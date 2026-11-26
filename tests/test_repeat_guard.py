"""Runaway guards: an identical tool call repeated within one turn is refused, and a
SPARQL query that mis-declares a palimpsest prefix gets a corrective note. Offline."""

from __future__ import annotations

import pytest

from palimpsest.agent import Agent, MaxTurnsExceeded
from palimpsest.cost import CostMeter
from palimpsest.providers.anthropic import LLMResponse


@pytest.fixture(autouse=True)
def _isolate_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    from palimpsest.tools import TOOLS
    TOOLS["count_me"] = count_me  # registered only while these tests run
    yield
    TOOLS.pop("count_me", None)


CALLS = {"n": 0}


def count_me(q: str = "") -> str:
    CALLS["n"] += 1
    return "same result"


count_me.tool_schema = {
    "name": "count_me", "description": "test tool that counts its executions",
    "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
}


class _SameCall:
    name = "stub"

    def __init__(self, inputs):
        self.inputs = inputs
        self.i = 0

    def complete(self, system, messages, tools, cache_breakpoints, on_text=None):
        inp = self.inputs[min(self.i, len(self.inputs) - 1)]
        self.i += 1
        call = {"id": f"t{self.i}", "name": "count_me", "input": inp}
        return LLMResponse(text="", tool_calls=[call],
                           usage={"input_tokens": 0, "output_tokens": 0},
                           raw={"content": [{"type": "tool_use", **call}]})


def test_identical_call_refused_after_two(tmp_path):
    CALLS["n"] = 0
    events = []
    agent = Agent(_SameCall([{"q": "x"}]), CostMeter(str(tmp_path / "c.db")),
                  tools={"count_me": count_me.tool_schema}, max_turns=6,
                  on_event=events.append)
    with pytest.raises(MaxTurnsExceeded):
        agent.run("go")
    assert CALLS["n"] == 2  # executed twice, then refused
    refused = [e for e in events if e["type"] == "tool_result" and "[repeat]" in e["content"]]
    assert len(refused) == 4 and all(e["is_error"] for e in refused)


def test_different_arguments_are_not_refused(tmp_path):
    CALLS["n"] = 0
    agent = Agent(_SameCall([{"q": str(i)} for i in range(5)]), CostMeter(str(tmp_path / "c.db")),
                  tools={"count_me": count_me.tool_schema}, max_turns=5)
    with pytest.raises(MaxTurnsExceeded):
        agent.run("go")
    assert CALLS["n"] == 5


def test_repeat_count_resets_each_run(tmp_path):
    CALLS["n"] = 0
    agent = Agent(_SameCall([{"q": "x"}]), CostMeter(str(tmp_path / "c.db")),
                  tools={"count_me": count_me.tool_schema}, max_turns=2)
    for _ in range(2):
        with pytest.raises(MaxTurnsExceeded):
            agent.run("go")
    assert CALLS["n"] == 4  # two per run: the guard is per user request


def test_sparql_wrong_prefix_gets_a_note(monkeypatch):
    import palimpsest.store as store_mod
    from palimpsest.tools.sparql_query import sparql_query

    class _S:
        def __init__(self, *_a):
            pass

        def sparql(self, q):
            return []

    monkeypatch.setattr(store_mod, "RDFStore", _S)
    out = sparql_query("PREFIX prov: <https://www.w3.org/ns/prov#>\nSELECT * WHERE { ?s ?p ?o }")
    assert "prov:" in out and "http://www.w3.org/ns/prov#" in out and out.startswith("note:")
    ok = sparql_query("PREFIX prov: <http://www.w3.org/ns/prov#>\nSELECT * WHERE { ?s ?p ?o }")
    assert not ok.startswith("note:")
