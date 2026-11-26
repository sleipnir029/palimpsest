"""The €-cap is checked BEFORE every paid call, not only once per agent turn:
the extraction LLM call and the RunPod pod are refused up front when the projected
spend would pass the cap. Offline: no LLM, no RunPod.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from palimpsest.cost import BudgetExceeded, CostMeter


def _meter_at_cap(tmp_path, spent=49.99):
    m = CostMeter(str(tmp_path / "cost.db"))
    m.record_llm("seed", spent, detail="seed")
    return m


# ----- extraction LLM call ---------------------------------------------------

class _NeverCall:
    name = "never"
    prices = {"input_tokens": 3.0 / 1e6, "output_tokens": 15.0 / 1e6}
    max_tokens = 4096

    def complete(self, **_kw):
        raise AssertionError("provider must not be called past the cap")


def test_extract_refuses_before_calling_the_model(tmp_path):
    from palimpsest.cache import ParserCache
    from palimpsest.tools.extract import extract

    sha = "a" * 64
    d = tmp_path / "cache" / sha
    d.mkdir(parents=True)
    (d / "mineru.json").write_text(json.dumps([[
        {"type": "text", "content": "eta = 236 mV at 10 mA cm-2", "bbox": [0, 0, 10, 10]}]]))
    cache = ParserCache(str(tmp_path / "p.db"), tmp_path / "cache")
    with pytest.raises(BudgetExceeded):
        extract(sha, "mineru", provider=_NeverCall(), cache=cache,
                cost_meter=_meter_at_cap(tmp_path))


def test_extract_allowed_with_headroom_records_spend(tmp_path):
    from palimpsest.cache import ParserCache
    from palimpsest.providers.anthropic import LLMResponse
    from palimpsest.tools.extract import extract

    class _Cheap(_NeverCall):
        def complete(self, **_kw):
            return LLMResponse(text='{"items": []}', tool_calls=[],
                               usage={"input_tokens": 10, "output_tokens": 5}, raw={})

    sha = "b" * 64
    d = tmp_path / "cache" / sha
    d.mkdir(parents=True)
    (d / "mineru.json").write_text(json.dumps([[
        {"type": "text", "content": "eta = 236 mV", "bbox": [0, 0, 10, 10]}]]))
    cache = ParserCache(str(tmp_path / "p.db"), tmp_path / "cache")
    meter = CostMeter(str(tmp_path / "cost.db"))
    extract(sha, "mineru", provider=_Cheap(), cache=cache, cost_meter=meter)
    assert meter.total_eur() > 0


# ----- RunPod pod --------------------------------------------------------------

def test_pod_refused_before_creation(tmp_path, monkeypatch):
    from palimpsest.parsers import gpu_provider

    monkeypatch.setenv("RUNPOD_API_KEY", "test")
    s = gpu_provider.RunPodSession(_meter_at_cap(tmp_path), template_id="t", idle_hard=2400)
    monkeypatch.setattr(s, "_start_pod",
                        lambda: (_ for _ in ()).throw(AssertionError("pod must not start")))
    with pytest.raises(BudgetExceeded):
        s.__enter__()


def test_runner_does_not_swallow_budget_refusal(tmp_path, monkeypatch):
    from palimpsest.cache import ParserCache
    from palimpsest.parsers import runner

    for p in ("DOCLING", "MINERU", "CHANDRA", "DOTS", "PADDLE"):
        monkeypatch.setenv(f"RUNPOD_TEMPLATE_{p}", "t")

    class _Refuse:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            raise BudgetExceeded(49.99, 50.0, 0.6)

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(runner, "RunPodSession", _Refuse)
    cache = ParserCache(str(tmp_path / "p.db"), tmp_path / "cache")
    pdf = Path(__file__).parent / "fixtures" / "sample.pdf"
    with pytest.raises(BudgetExceeded):
        runner.parse_with_cache([pdf], CostMeter(str(tmp_path / "c.db")), cache)


# ----- bring-your-own-agent stays free --------------------------------------------

def test_external_ingest_not_refused_near_cap():
    from palimpsest.agent import _cost_eur
    from palimpsest.external import _Replay

    p = _Replay("{}")
    assert _cost_eur({"input_tokens": 50_000, "output_tokens": 16_000}, p.prices) == 0.0


def test_extract_tool_path_is_metered(tmp_path, monkeypatch):
    """The agent's `extract` tool passes no cost_meter: the config-resolved provider is
    still a paid call, so it must be checked against (and recorded in) the ledger."""
    import palimpsest.cost as cost
    import palimpsest.tools.extract as ex
    from palimpsest.cache import ParserCache

    monkeypatch.setattr(cost, "_CANONICAL_DB", str(tmp_path / "c.db"))
    CostMeter("palimpsest.db").record_llm("seed", 49.99)
    monkeypatch.setattr(ex, "_resolve_extraction_provider", lambda db="": _NeverCall())
    sha = "c" * 64
    d = tmp_path / "cache" / sha
    d.mkdir(parents=True)
    (d / "mineru.json").write_text(json.dumps([[
        {"type": "text", "content": "eta = 236 mV", "bbox": [0, 0, 10, 10]}]]))
    cache = ParserCache(str(tmp_path / "p.db"), tmp_path / "cache")
    with pytest.raises(BudgetExceeded):
        ex.extract(sha, "mineru", cache=cache)  # no cost_meter, like Agent._dispatch


def test_free_ingest_allowed_even_over_cap(tmp_path):
    """A €0 bring-your-own-agent call is never refused, even if spend is already over."""
    from palimpsest.cache import ParserCache
    from palimpsest.external import _Replay
    from palimpsest.tools.extract import extract

    sha = "d" * 64
    d = tmp_path / "cache" / sha
    d.mkdir(parents=True)
    (d / "mineru.json").write_text(json.dumps([[
        {"type": "text", "content": "eta = 236 mV", "bbox": [0, 0, 10, 10]}]]))
    cache = ParserCache(str(tmp_path / "p.db"), tmp_path / "cache")
    meter = _meter_at_cap(tmp_path, spent=50.20)  # already over the €50 cap
    extract(sha, "mineru", provider=_Replay('{"items": []}'), cache=cache, cost_meter=meter)


def test_pod_rechecked_with_real_rate(tmp_path, monkeypatch):
    """A pricier GPU than the $1/h ceiling is refused once its real rate is known,
    and the pod is torn down."""
    from palimpsest.parsers import gpu_provider

    monkeypatch.setenv("RUNPOD_API_KEY", "test")
    meter = _meter_at_cap(tmp_path, spent=48.5)  # $1/h projection (~€0.6) fits, $5/h doesn't
    s = gpu_provider.RunPodSession(meter, template_id="t", idle_hard=2400)
    stopped = []
    monkeypatch.setattr(s, "_start_pod", lambda: setattr(s, "pod_id", "p1"))
    monkeypatch.setattr(s, "_await_running", lambda: {"costPerHr": 5.0})
    monkeypatch.setattr(s, "_connect_ssh", lambda pod: (_ for _ in ()).throw(AssertionError("no ssh")))
    monkeypatch.setattr(s._client, "post", lambda url, **k: stopped.append(url))
    with pytest.raises(BudgetExceeded):
        s.__enter__()
    assert any(u.endswith("/pods/p1/stop") for u in stopped)


def test_budget_refusal_in_tool_is_labelled(tmp_path):
    from palimpsest.agent import Agent

    agent = Agent(provider=None, cost_meter=CostMeter(str(tmp_path / "c.db")), tools={})
    import palimpsest.agent as agent_mod

    def _refusing_tool(**_):
        raise BudgetExceeded(49.99, 50.0, 0.1)
    _refusing_tool.tool_schema = {"input_schema": {"type": "object"}}
    orig = dict(agent_mod.TOOLS)
    agent_mod.TOOLS["_refuse"] = _refusing_tool
    try:
        out = agent._dispatch({"id": "t1", "name": "_refuse", "input": {}})
    finally:
        agent_mod.TOOLS.clear(); agent_mod.TOOLS.update(orig)
    assert out["is_error"] and "[budget]" in out["content"]
