"""T17 — cache-hit verification.

Budget-critical invariant: once every (sha × parser) cell is cached, a re-run of
`parse_with_cache` must NOT spin a single pod. Prove it by patching
`runner.RunPodSession` to a sentinel whose `__init__` AND `__enter__` raise — if
the runner short-circuits correctly, the sentinel is never touched and nothing
fires. Belt-and-suspenders: also assert `cost_meter.total_eur()` is unchanged
between calls.

The test runs `parse_with_cache` TWICE on a single PDF in a fresh `tmp_path`:
- Call 1: `_FakePodSession` (mocked, materializes outputs) populates the cache.
- Call 2: `_PoisonedPodSession` — must never be instantiated nor entered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from palimpsest.cache import ParserCache
from palimpsest.cost import CostMeter
from palimpsest.parsers import runner
from palimpsest.parsers.commands import PARSERS

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


class _FakePodSession:
    """Minimal RunPodSession stand-in for the FIRST call: materializes outputs
    so the runner's cache insert + `cache.get_output` lookups succeed."""

    def __init__(self, cost_meter, template_id=None, gpu_type=None, cloud=None,
                 idle_soft=60, idle_hard=300, **kwargs):
        self.usd_per_hour = 0.46  # non-zero so any cost math works; not asserted
        self.pending_work = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ssh(self, cmd, timeout=600):
        return "ok\n"

    def scp_up(self, local, remote):
        pass

    def scp_down(self, remote, local):
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_text("fake parser output")


class _PoisonedPodSession:
    """The load-bearing sentinel for the SECOND call. If the cache short-circuit
    ever regresses, EITHER raise fires — and the test reports loudly which
    failure mode hit (constructor or context entry)."""

    def __init__(self, *args, **kwargs):
        raise AssertionError(
            "cache miss: RunPodSession was instantiated on second call "
            "(cache short-circuit regressed)"
        )

    def __enter__(self):
        raise AssertionError(
            "cache miss: RunPodSession.__enter__ was called on second call "
            "(cache short-circuit regressed)"
        )

    def __exit__(self, *exc):
        return False


@pytest.fixture
def env(monkeypatch):
    for parser in ("DOCLING", "MINERU", "CHANDRA", "DOTS", "PADDLE"):
        monkeypatch.setenv(f"RUNPOD_TEMPLATE_{parser}", f"tmpl-{parser.lower()}")
    monkeypatch.setenv("RUNPOD_API_KEY", "test")
    monkeypatch.setenv("RUNPOD_GPU", "NVIDIA GeForce RTX 3090")
    monkeypatch.setenv("RUNPOD_CLOUD", "secure")


def test_second_call_uses_cache(tmp_path, env, monkeypatch, capsys):
    cache = ParserCache(str(tmp_path / "cache.db"), tmp_path / "cache")
    meter = CostMeter(str(tmp_path / "cost.db"))

    # First call: fake pods materialize outputs → cache populates.
    monkeypatch.setattr(runner, "RunPodSession", _FakePodSession)
    first = runner.parse_with_cache([FIXTURE], meter, cache)
    sha = next(iter(first))
    assert set(first[sha].keys()) == set(PARSERS), "first call must fill every cell"

    before = meter.total_eur()

    # Second call: ANY touch of RunPodSession raises AssertionError.
    monkeypatch.setattr(runner, "RunPodSession", _PoisonedPodSession)
    second = runner.parse_with_cache([FIXTURE], meter, cache)

    after = meter.total_eur()

    assert before == after, (
        f"ledger changed across cached re-run: before €{before} != after €{after}"
    )
    assert set(second[sha].keys()) == set(PARSERS), "second call must return full mapping from cache"
    print("second call used cache")
