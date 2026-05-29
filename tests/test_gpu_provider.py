"""T14 RunPodSession. Dry-run mocks the RunPod REST API + SSH; the live test
(marked `live`, skipped unless --live) starts a real pod for ~$0.05.
"""

import hashlib
import os
import time
import types

import httpx
import pytest
from dotenv import load_dotenv

from palimpsest.cost import CostMeter
from palimpsest.parsers import gpu_provider
from palimpsest.parsers.gpu_provider import RunPodSession


# -- fakes for the dry-run ---------------------------------------------------
class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _fake_post(self, url, **kw):
    if url.endswith("/stop"):
        return _Resp({})
    return _Resp({"id": "fake-pod"})  # POST /pods


def _fake_get(self, url, **kw):
    # First poll already reports ready, so _await_running never sleeps.
    return _Resp(
        {
            "desiredStatus": "RUNNING",
            "publicIp": "1.2.3.4",
            "portMappings": {"22": 10000},
            "costPerHr": 0.34,
            "adjustedCostPerHr": 0.34,
        }
    )


class _FakeConn:
    def __init__(self, **kw):
        self.client = types.SimpleNamespace(set_missing_host_key_policy=lambda *a: None)

    def open(self):
        pass

    def run(self, command, **kw):
        return types.SimpleNamespace(stdout=f"ran: {command}\n")

    def put(self, *a):
        pass

    def get(self, *a):
        pass

    def close(self):
        pass


def test_lifecycle_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    monkeypatch.setattr(httpx.Client, "post", _fake_post)
    monkeypatch.setattr(httpx.Client, "get", _fake_get)
    monkeypatch.setattr(gpu_provider, "Connection", _FakeConn)

    meter = CostMeter(str(tmp_path / "gpu.db"))
    # High idle thresholds so the watchdog never fires during the short test.
    with RunPodSession(
        meter, template_id="tmpl-x", idle_soft=9999, idle_hard=9999
    ) as pod:
        assert pod.pod_id == "fake-pod"
        assert pod.usd_per_hour == 0.34
        assert "echo hi" in pod.ssh("echo hi")

    # Billed exactly once, as a GPU entry tagged pod_session, for > 0 EUR.
    rows = meter.conn.execute(
        "SELECT amount_eur, detail FROM cost_ledger WHERE kind = 'gpu'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] > 0
    assert rows[0][1] == "pod_session"


def test_watchdog_idle_soft_bills_from_main_thread(tmp_path, monkeypatch):
    """Watchdog teardown must bill exactly once, written on the entering thread
    (the watchdog thread cannot touch CostMeter's thread-affine SQLite conn)."""
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    monkeypatch.setattr(httpx.Client, "post", _fake_post)
    monkeypatch.setattr(httpx.Client, "get", _fake_get)
    monkeypatch.setattr(gpu_provider, "Connection", _FakeConn)

    meter = CostMeter(str(tmp_path / "gpu.db"))
    # idle_soft=0 + no activity → watchdog fires idle_soft_stop on its first 5s tick.
    with RunPodSession(meter, idle_soft=0, idle_hard=9999) as pod:
        time.sleep(6)
        assert pod._torn_down  # watchdog tore the pod down, not __exit__

    rows = meter.conn.execute(
        "SELECT amount_eur, detail FROM cost_ledger WHERE kind = 'gpu'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "idle_soft_stop"
    assert rows[0][0] > 0


def test_bill_written_even_when_stop_fails(tmp_path, monkeypatch):
    """A failing pod-stop call must not swallow the bill: _flush_bill runs in a
    finally, so the ledger entry lands even though the stop exception propagates."""

    def _post_stop_raises(self, url, **kw):
        if url.endswith("/stop"):
            raise httpx.ConnectError("stop boom")
        return _Resp({"id": "fake-pod"})

    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    monkeypatch.setattr(httpx.Client, "post", _post_stop_raises)
    monkeypatch.setattr(httpx.Client, "get", _fake_get)
    monkeypatch.setattr(gpu_provider, "Connection", _FakeConn)

    meter = CostMeter(str(tmp_path / "gpu.db"))
    with pytest.raises(httpx.ConnectError):  # stop failure surfaces loudly
        with RunPodSession(meter, idle_soft=9999, idle_hard=9999) as pod:
            pod.ssh("echo hi")

    rows = meter.conn.execute(
        "SELECT amount_eur, detail FROM cost_ledger WHERE kind = 'gpu'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "pod_session"
    assert rows[0][0] > 0


@pytest.mark.live
def test_real_pod_short(tmp_path):
    load_dotenv()
    # GPU availability is dynamic: pass a cheapest-first list (comma-separated in
    # RUNPOD_GPU) so RunPod allocates whatever is in stock. Cloud via RUNPOD_CLOUD.
    gpus = [g.strip() for g in os.environ.get(
        "RUNPOD_GPU", "NVIDIA GeForce RTX 4090").split(",")]
    cloud = os.environ.get("RUNPOD_CLOUD", "community")
    meter = CostMeter(str(tmp_path / "gpu.db"))
    # template_id falls back to RUNPOD_TEMPLATE_ID.
    with RunPodSession(meter, gpu_type=gpus, cloud=cloud) as pod:
        assert "hello" in pod.ssh("echo hello")

    rows = meter.conn.execute(
        "SELECT amount_eur FROM cost_ledger WHERE kind = 'gpu'"
    ).fetchall()
    assert len(rows) == 1
    # Default cap is the card's €0.10 (cheap GPU); RUNPOD_MAX_EUR raises it when
    # only a pricier GPU is deployable.
    max_eur = float(os.environ.get("RUNPOD_MAX_EUR", "0.10"))
    assert 0 < meter.total_eur() < max_eur


@pytest.mark.live
def test_scp_round_trip(tmp_path):
    """Prove scp_up + ssh + scp_down: upload a file, hash it on the pod, download
    it back, and confirm the bytes survive the round trip."""
    load_dotenv()
    gpus = [g.strip() for g in os.environ.get(
        "RUNPOD_GPU", "NVIDIA GeForce RTX 4090").split(",")]
    cloud = os.environ.get("RUNPOD_CLOUD", "community")

    content = f"palimpsest scp round-trip {os.getpid()}\n".encode()
    want = hashlib.md5(content).hexdigest()
    up = tmp_path / "up.bin"
    up.write_bytes(content)
    down = tmp_path / "down.bin"

    meter = CostMeter(str(tmp_path / "gpu.db"))
    with RunPodSession(meter, gpu_type=gpus, cloud=cloud) as pod:
        pod.scp_up(up, "/root/rt.bin")
        remote_md5 = pod.ssh("md5sum /root/rt.bin").split()[0]
        assert remote_md5 == want  # scp_up delivered the bytes intact
        pod.scp_down("/root/rt.bin", down)

    assert down.read_bytes() == content  # scp_down round-tripped intact
