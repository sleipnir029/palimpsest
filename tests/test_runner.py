"""T16 parse_with_cache — mocked gpu_provider, no live calls.

Three cases per the card:
- happy path: empty cache, all 5 parsers spin a pod, complete mapping
- all-cached short-circuit: pre-populated cache, RunPodSession NEVER instantiated
- mixed/per-parser skip: one parser fully cached → pod skipped; others run; mapping complete

The mock `_FakePodSession` records each instance so the test can assert which template
IDs were used (one per parser) and which were skipped.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from palimpsest.cache import ParserCache
from palimpsest.cost import CostMeter
from palimpsest.parsers import runner
from palimpsest.parsers.commands import PARSERS

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


class _FakePodSession:
    """Stands in for RunPodSession. Records instantiation + commands for inspection."""

    instances: list["_FakePodSession"] = []

    def __init__(self, cost_meter, template_id=None, gpu_type=None, cloud=None,
                 idle_soft=60, idle_hard=300, **kwargs):
        self.template_id = template_id
        self.usd_per_hour = 0.46  # arbitrary non-zero so cost computation works
        self.pending_work = False
        self.ssh_calls: list[str] = []
        self.scp_up_calls: list[tuple] = []
        self.scp_down_calls: list[tuple] = []
        _FakePodSession.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ssh(self, cmd, timeout=600):
        self.ssh_calls.append(cmd)
        return "ok\n"

    def scp_up(self, local, remote):
        self.scp_up_calls.append((str(local), remote))

    def scp_down(self, remote, local):
        self.scp_down_calls.append((remote, str(local)))
        # Simulate the parser writing output: materialize the local file so the
        # runner's `local_path.relative_to(cache_dir)` + cache insert succeed and
        # later `cache.get_output` sees an existing path.
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_text("fake parser output")


@pytest.fixture
def env(monkeypatch):
    # Distinct fake template IDs per parser so tests can assert which were used.
    for parser in ("DOCLING", "MINERU", "CHANDRA", "DOTS", "PADDLE"):
        monkeypatch.setenv(f"RUNPOD_TEMPLATE_{parser}", f"tmpl-{parser.lower()}")
    monkeypatch.setenv("RUNPOD_API_KEY", "test")
    monkeypatch.setenv("RUNPOD_GPU", "NVIDIA GeForce RTX 3090")
    monkeypatch.setenv("RUNPOD_CLOUD", "secure")


@pytest.fixture
def fake_pod(monkeypatch):
    _FakePodSession.instances = []
    monkeypatch.setattr(runner, "RunPodSession", _FakePodSession)
    return _FakePodSession


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _prepopulate(cache, sha, parser_names, cache_dir):
    """Insert a parser_runs row + materialize the output file for each parser_name."""
    for parser in parser_names:
        d = cache_dir / sha
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{parser}.json").write_text("cached")
        cache.insert_parser_run(
            sha256=sha,
            parser_name=parser,
            parser_ver=PARSERS[parser]["version"],
            output_path=f"{sha}/{parser}.json",
            gpu_seconds=0.0,
            gpu_cost_eur=0.0,
            run_id="prepop",
        )


def test_happy_path(tmp_path, env, fake_pod):
    """Empty cache → 5 pods (one per parser), mapping COMPLETE for every cell."""
    cache = ParserCache(str(tmp_path / "cache.db"), tmp_path / "cache")
    meter = CostMeter(str(tmp_path / "cost.db"))

    result = runner.parse_with_cache([FIXTURE], meter, cache)

    sha = next(iter(result))
    assert len(fake_pod.instances) == len(PARSERS)
    template_ids = sorted(p.template_id for p in fake_pod.instances)
    assert template_ids == sorted(
        f"tmpl-{p}" for p in PARSERS
    )
    assert set(result[sha].keys()) == set(PARSERS)


def test_all_cached_short_circuit(tmp_path, env, fake_pod):
    """Cache holds all 5 parsers → no pod is ever instantiated."""
    cache = ParserCache(str(tmp_path / "cache.db"), tmp_path / "cache")
    meter = CostMeter(str(tmp_path / "cost.db"))
    sha = _sha(FIXTURE)
    cache.add_paper(sha, FIXTURE.name, 12)
    _prepopulate(cache, sha, PARSERS.keys(), tmp_path / "cache")

    result = runner.parse_with_cache([FIXTURE], meter, cache)

    assert fake_pod.instances == []  # the load-bearing assertion
    assert set(result[sha].keys()) == set(PARSERS)


def test_one_parser_failure_omits_cell_and_continues(tmp_path, env, fake_pod, monkeypatch):
    """The card's distinctive spec: if a parser fails on a paper, log + continue with
    the others; do NOT crash. The failed cell is omitted (no parser_runs row → future
    retry stays open). All 5 pods still get attempted; only the failing parse breaks."""
    real_ssh = _FakePodSession.ssh

    def selective_ssh(self, cmd, timeout=600):
        if "chandra" in cmd:
            raise RuntimeError("simulated chandra OOM")
        return real_ssh(self, cmd, timeout)

    monkeypatch.setattr(_FakePodSession, "ssh", selective_ssh)

    cache = ParserCache(str(tmp_path / "cache.db"), tmp_path / "cache")
    meter = CostMeter(str(tmp_path / "cost.db"))
    result = runner.parse_with_cache([FIXTURE], meter, cache)

    sha = next(iter(result))
    # Other 4 succeed; chandra cell omitted, not crashed, not filled with None.
    assert set(result[sha].keys()) == set(PARSERS) - {"chandra"}
    # No parser_runs row written for the failed pair → retry stays open.
    assert cache.get_output(sha, "chandra") is None
    # All 5 pods still attempted (failure doesn't short-circuit the outer loop).
    assert len(fake_pod.instances) == len(PARSERS)


def test_mixed_per_parser_skip(tmp_path, env, fake_pod):
    """One parser cached → its pod is skipped; the other 4 run; mapping complete."""
    cache = ParserCache(str(tmp_path / "cache.db"), tmp_path / "cache")
    meter = CostMeter(str(tmp_path / "cost.db"))
    sha = _sha(FIXTURE)
    cache.add_paper(sha, FIXTURE.name, 12)
    _prepopulate(cache, sha, ["docling"], tmp_path / "cache")

    result = runner.parse_with_cache([FIXTURE], meter, cache)

    assert len(fake_pod.instances) == len(PARSERS) - 1
    template_ids = sorted(p.template_id for p in fake_pod.instances)
    assert "tmpl-docling" not in template_ids
    # The invariant: every sha × every parser cell is filled, mix of cache + fresh.
    assert set(result[sha].keys()) == set(PARSERS)
    # docling cell came from cache (the prepopulated file).
    assert "docling.json" in str(result[sha]["docling"])
