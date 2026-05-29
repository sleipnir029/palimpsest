"""RunPodSession: start a RunPod GPU pod, run work over SSH, tear down + bill. T14.

Parser-agnostic — T16 passes the per-parser `template_id`. The pod is started only
on `__enter__`, torn down aggressively by an idle watchdog, and every wall-second is
billed to the CostMeter at the pod's *actual* hourly rate (read off the pod object,
never hardcoded). The caller loads the env (RUNPOD_API_KEY etc.); this module does
not, matching tests/test_e2e.py.

Billing is computed wherever teardown happens (any thread, in-memory) but the DB
write goes through `_flush_bill` on the *entering* thread only — CostMeter's SQLite
connection is thread-affine, so the watchdog thread must never call `record_gpu`.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import httpx
from fabric import Connection
from paramiko import AutoAddPolicy

RUNPOD_API = "https://rest.runpod.io/v1"
# Separate FX snapshot for GPU spend (card). Mirrors agent._USD_TO_EUR by value
# but kept local so a parser never imports from the agent.
EUR_PER_USD = 0.92


class RunPodSession:
    def __init__(
        self,
        cost_meter,
        template_id: str | None = None,
        gpu_type: str | list[str] = "NVIDIA GeForce RTX 4090",
        cloud: str = "community",
        idle_soft: int = 60,
        idle_hard: int = 300,
    ):
        self.cost_meter = cost_meter
        self.template_id = template_id or os.environ.get("RUNPOD_TEMPLATE_ID")
        self.gpu_type = gpu_type
        self.cloud = cloud
        self.idle_soft = idle_soft
        self.idle_hard = idle_hard
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"},
            timeout=30.0,
        )
        # T16's batch runner MUST set this True around any ssh() call that runs
        # longer than idle_soft, else the watchdog tears the pod down mid-command.
        self.pending_work = False
        self.last_activity: float | None = None
        self.connect_ts: float | None = None
        self.usd_per_hour: float | None = None
        self.pod_id: str | None = None
        self._conn: Connection | None = None
        self._torn_down = False
        self._lock = threading.Lock()
        self._pending_eur: float | None = None  # computed at teardown, written by _flush_bill
        self._pending_detail = "pod_session"
        self._bill_written = False

    # -- lifecycle -----------------------------------------------------------
    def __enter__(self) -> RunPodSession:
        try:
            self._start_pod()
            pod = self._await_running()
            self.usd_per_hour = pod.get("adjustedCostPerHr") or pod.get("costPerHr")
            if not self.usd_per_hour:
                raise RuntimeError(
                    f"pod {self.pod_id} returned no usable hourly rate; refusing to bill"
                )
            # Bill from here: the SSH-handshake retries below are already on the clock.
            self.connect_ts = self.last_activity = time.time()
            self._conn = self._connect_ssh(pod)
            threading.Thread(target=self._watchdog, daemon=True).start()
            return self
        except BaseException:  # incl. KeyboardInterrupt: never leak a running pod
            try:
                self._teardown("setup_failed")
            finally:
                self._flush_bill()  # bill even if the stop call raised
            raise

    def __exit__(self, *exc) -> bool:
        try:
            self._teardown("pod_session")  # no-op if the watchdog already tore down
        finally:
            self._flush_bill()  # entering thread → safe DB write, exactly once
        return False  # re-raise anything that escaped the with-body

    def _teardown(self, detail: str) -> None:
        """Stop the pod and compute (but do not write) the bill. Safe on any thread."""
        with self._lock:  # watchdog vs __exit__: exactly one wins
            if self._torn_down:
                return
            self._torn_down = True
            if self.connect_ts and self.usd_per_hour:  # only a started pod is billed
                wall = time.time() - self.connect_ts
                self._pending_eur = wall / 3600 * self.usd_per_hour * EUR_PER_USD
                self._pending_detail = detail
        # network + IO outside the lock
        try:
            if self.pod_id:
                self._client.post(f"{RUNPOD_API}/pods/{self.pod_id}/stop")
        finally:
            if self._conn is not None:
                self._conn.close()
            self._client.close()

    def _flush_bill(self) -> None:
        """Write the computed bill to the CostMeter. Entering-thread only, once."""
        with self._lock:
            if self._bill_written or self._pending_eur is None:
                return
            self._bill_written = True
            eur, detail = self._pending_eur, self._pending_detail
        self.cost_meter.record_gpu(eur, detail=detail)

    # -- RunPod REST ---------------------------------------------------------
    def _start_pod(self) -> None:
        # A list lets RunPod allocate whichever GPU is in stock (availability is
        # dynamic); a bare str is wrapped to a 1-element list.
        gpu_ids = [self.gpu_type] if isinstance(self.gpu_type, str) else list(self.gpu_type)
        body = {
            "cloudType": self.cloud.upper(),  # enum COMMUNITY | SECURE
            "gpuTypeIds": gpu_ids,
            "gpuCount": 1,
            "computeType": "GPU",
            "ports": ["22/tcp"],  # expose SSH
        }
        if self.template_id:
            body["templateId"] = self.template_id
        r = self._client.post(f"{RUNPOD_API}/pods", json=body)
        r.raise_for_status()
        self.pod_id = r.json()["id"]  # set on self so teardown can always stop it

    def _await_running(self, tries: int = 60, delay: int = 5) -> dict:
        for _ in range(tries):
            r = self._client.get(f"{RUNPOD_API}/pods/{self.pod_id}")
            r.raise_for_status()
            pod = r.json()
            if (
                pod.get("desiredStatus") == "RUNNING"
                and pod.get("publicIp")
                and (pod.get("portMappings") or {}).get("22")
            ):
                return pod
            time.sleep(delay)
        raise TimeoutError(f"pod {self.pod_id} not SSH-ready after {tries * delay}s")

    # -- SSH -----------------------------------------------------------------
    def _connect_ssh(self, pod: dict, tries: int = 10, delay: int = 3) -> Connection:
        key = os.environ.get("RUNPOD_SSH_KEY", os.path.expanduser("~/.ssh/id_ed25519"))
        conn = Connection(
            host=pod["publicIp"],
            user="root",
            port=int(pod["portMappings"]["22"]),
            connect_kwargs={"key_filename": key},
        )
        conn.client.set_missing_host_key_policy(AutoAddPolicy())  # pods rotate host keys
        last = None
        for _ in range(tries):  # status RUNNING != sshd accepting connections yet
            try:
                conn.open()
                return conn
            except Exception as e:  # noqa: BLE001 — any connect failure is retryable
                last = e
                time.sleep(delay)
        raise RuntimeError(f"pod {self.pod_id} sshd not ready: {last}")

    def ssh(self, command: str, timeout: int = 600) -> str:
        self._touch()
        # in_stream=False: commands are non-interactive, so never forward stdin —
        # forwarding raises OSError under captured stdin (pytest/CI/automation).
        return self._conn.run(
            command, hide=True, timeout=timeout, in_stream=False
        ).stdout

    def scp_up(self, local: Path, remote: str) -> None:
        self._touch()
        self._conn.put(str(local), remote)

    def scp_down(self, remote: str, local: Path) -> None:
        self._touch()
        self._conn.get(remote, str(local))

    def _touch(self) -> None:
        self.last_activity = time.time()

    # -- watchdog ------------------------------------------------------------
    def _watchdog(self) -> None:
        while not self._torn_down:
            time.sleep(5)
            if self._torn_down:
                break
            idle = time.time() - self.last_activity
            if idle > self.idle_hard:
                self._teardown("idle_hard_kill")  # billed later by _flush_bill
                break
            if idle > self.idle_soft and not self.pending_work:
                self._teardown("idle_soft_stop")
                break
