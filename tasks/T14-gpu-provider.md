# T14 — gpu_provider context manager + idle watchdog

## Why
Tight GPU lifecycle is the biggest cost lever after the parse-once cache. Pods start only when needed, get torn down aggressively, and every wall-second is logged.

## Architecture note
The four parsers are **isolated images** (docling/mineru/chandra built; olmocr upstream), so
one pod = one parser image. `RunPodSession` is parser-agnostic — the caller (T16) passes the
right `template_id` per parser. Convention: one RunPod template per parser, its ID in env as
`RUNPOD_TEMPLATE_<PARSER>` (e.g. `RUNPOD_TEMPLATE_DOCLING`). The batch-by-parser runner starts
one session per parser and runs the whole corpus through it before tearing down.

## Input state
- T13 merged. All four RunPod templates are registered (docling/mineru/chandra/olmocr-upstream).
- T05 merged. CostMeter records GPU spend.

## Output state
- File `src/palimpsest/parsers/gpu_provider.py` exports:
  - Class `RunPodSession`:
    - `__init__(self, cost_meter, template_id: str | None = None, gpu_type: str = "NVIDIA GeForce RTX 4090", cloud: str = "community", idle_soft: int = 60, idle_hard: int = 300)`.
    - Reads `RUNPOD_API_KEY` from env. `template_id` is supplied by the caller: the T16 runner resolves it per parser from `RUNPOD_TEMPLATE_<PARSER>` via the registry. A bare `RUNPOD_TEMPLATE_ID` env may seed it only for ad-hoc single-pod tests (there is no single shared template in the four-image world).
    - `__enter__` — calls RunPod REST API `POST /pods` to start; polls `GET /pods/{id}` until status is `RUNNING` and SSH port is exposed; records `self.connect_ts`. **Reads the pod's actual hourly rate** from the pod object (`self.usd_per_hour = pod["adjustedCostPerHr"] or pod["costPerHr"]`) — do NOT hardcode a rate; it varies by GPU type and cloud (community/secure/spot). Spawns idle watchdog thread.
    - `__exit__` — calls `POST /pods/{id}/stop`; computes wall_seconds; converts to EUR as `wall_seconds/3600 × self.usd_per_hour × EUR_PER_USD` (RunPod credits are USD-denominated, funded in dollars at par); calls `cost_meter.record_gpu(eur, detail="pod_session")`. `EUR_PER_USD` is a separate FX snapshot.
    - `def ssh(self, command: str, timeout: int = 600) -> str` — runs command on pod via SSH (use `fabric` or plain `subprocess.run(["ssh", ...])`). Updates `self.last_activity` on each call.
    - `def scp_up(self, local: Path, remote: str) -> None` and `scp_down(self, remote: str, local: Path) -> None`.
    - `def _touch(self)` — updates `self.last_activity`.
  - Idle watchdog thread:
    - Every 5s, checks `time.time() - self.last_activity`.
    - If > `idle_hard` (default 5 min): teardown immediately with detail `idle_hard_kill`.
    - If > `idle_soft` (default 60s) AND no pending work flag: teardown with detail `idle_soft_stop`.
- File `tests/test_gpu_provider.py` covers:
  - `test_lifecycle_dry_run()` — with RunPod API mocked, exercise __enter__ / ssh / __exit__ paths.
  - `test_real_pod_short()` (marked `@pytest.mark.live` — skipped unless `--live` flag passed) — starts a real pod, runs `echo hello`, tears down. Verifies cost ledger has a GPU entry with > 0 EUR and < €0.10.

## Verification
```bash
pixi run pytest tests/test_gpu_provider.py -v
# (live test, run sparingly — costs ~$0.05)
pixi run pytest tests/test_gpu_provider.py -v --live -k test_real_pod_short
```
First command: all non-live tests pass. Second command (when run): the live test passes, the cost ledger entry is verified.

## Will touch
- `src/palimpsest/parsers/gpu_provider.py` (full implementation)
- `src/palimpsest/parsers/__init__.py` (edit: export RunPodSession)
- `tests/test_gpu_provider.py` (new)

## Will NOT touch
- Any other parser file (T16 builds on this).
- Cost meter (T05 stays as is — gpu_provider USES it, doesn't change it).

## Out of scope
- Running actual parsers inside the pod → T16.
- Caching parser results → T15.

## Notes / references
- RunPod REST API: https://rest.runpod.io/v1/docs
- Use `fabric` (already in pixi.toml? if not, add) or plain `subprocess.run`. Prefer `fabric` for SSH key auth.
- Watchdog runs in a daemon Thread; ensure it doesn't block exit.
- The `--live` pytest marker requires conftest.py: `def pytest_addoption(parser): parser.addoption("--live", action="store_true")`. Live tests skip unless flag is passed.
- Always handle KeyboardInterrupt — if user Ctrl+Cs during a pod session, tear down before re-raising.
