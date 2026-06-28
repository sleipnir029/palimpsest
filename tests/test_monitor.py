"""Tests for the SessionMonitor supervisor (demo observability wrapper).

Deterministic + free: stub providers drive the agent loop, a temp CostMeter gives
a fresh budget, and the monitor writes its logs into tmp_path. No network, no key.
"""

import json

import pytest

from palimpsest.agent import Agent
from palimpsest.cost import CostMeter
from palimpsest.monitor import SessionMonitor
from palimpsest.providers.anthropic import LLMResponse
from palimpsest.tools import register


@pytest.fixture(autouse=True)
def _isolate_workspace(tmp_path, monkeypatch):
    """Isolate the workspace so a constructed Agent's SessionLog (T66) writes into tmp
    (no .git there → no-op), never the real ./workspace/.palimpsest/session.jsonl.
    The SessionMonitor here already targets tmp via log_dir, but the Agent's own
    transcript would otherwise still pollute the real workspace."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))

_ZERO = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 0,
}


@register("mon_fails", {
    "description": "Always raises, to exercise an is_error tool result.",
    "input_schema": {"type": "object", "properties": {}},
})
def mon_fails() -> str:
    raise RuntimeError("boom")


class _OneToolThenDone:
    """Turn 1 calls the failing tool; turn 2 returns a final answer (loop ends)."""

    name = "stub"

    def __init__(self) -> None:
        self.turn = 0

    def complete(self, system, messages, tools, cache_breakpoints, on_text=None):
        self.turn += 1
        if self.turn == 1:
            call = {"id": "t1", "name": "mon_fails", "input": {}}
            return LLMResponse(
                text="", tool_calls=[call], usage=dict(_ZERO),
                raw={"content": [{"type": "tool_use", **call}]},
            )
        return LLMResponse(
            text="done", tool_calls=[], usage=dict(_ZERO),
            raw={"content": [{"type": "text", "text": "done"}]},
        )


class _Priced:
    """Finishes in one turn, reporting non-zero usage against a known price table."""

    name = "stub"
    prices = {"input_tokens": 1.0}  # €/token after the USD->EUR factor

    def complete(self, system, messages, tools, cache_breakpoints, on_text=None):
        return LLMResponse(
            text="hi", tool_calls=[], usage={**_ZERO, "input_tokens": 5},
            raw={"content": [{"type": "text", "text": "hi"}]},
        )


class _AlwaysCallsTool:
    """Never finishes — drives the loop to MaxTurnsExceeded."""

    name = "stub"

    def complete(self, system, messages, tools, cache_breakpoints, on_text=None):
        call = {"id": "t1", "name": "mon_fails", "input": {}}
        return LLMResponse(
            text="", tool_calls=[call], usage=dict(_ZERO),
            raw={"content": [{"type": "tool_use", **call}]},
        )


def test_observe_flags_tool_error_and_writes_log(tmp_path):
    """A tool_result with is_error becomes a recorded issue, and the tool name is
    written to both the human log and the jsonl sink."""
    meter = CostMeter(str(tmp_path / "c.db"))
    monitor = SessionMonitor(log_dir=tmp_path)
    agent = Agent(
        _OneToolThenDone(), meter,
        tools={"mon_fails": mon_fails.tool_schema},
        on_event=monitor.observe,
    )
    monitor.run(agent, "do it")

    tool_errors = [i for i in monitor.issues if i["kind"] == "tool_error"]
    assert len(tool_errors) == 1
    assert tool_errors[0]["tool"] == "mon_fails"

    log_text = next(tmp_path.glob("demo-*.log")).read_text()
    assert "mon_fails" in log_text
    jsonl = next(tmp_path.glob("demo-*.jsonl")).read_text().splitlines()
    kinds = [json.loads(line).get("type") for line in jsonl]
    assert "tool_call" in kinds and "tool_result" in kinds


def test_run_records_per_prompt_cost_delta(tmp_path):
    """run() snapshots spend before/after so each prompt has a € delta that matches
    the ledger movement (5 tokens * €1.0 * 0.92 = €4.60)."""
    meter = CostMeter(str(tmp_path / "c.db"))
    monitor = SessionMonitor(log_dir=tmp_path)
    agent = Agent(_Priced(), meter, tools={}, on_event=monitor.observe)

    monitor.run(agent, "hello")

    assert monitor.runs[-1]["cost_eur"] == round(meter.total_eur(), 4)
    assert monitor.runs[-1]["cost_eur"] > 0


def test_run_captures_exception_without_reraising(tmp_path):
    """A turn that blows up (here: MaxTurnsExceeded) is logged as an issue and the
    run is marked failed, but run() does NOT propagate — a demo sequence continues."""
    meter = CostMeter(str(tmp_path / "c.db"))
    monitor = SessionMonitor(log_dir=tmp_path)
    agent = Agent(
        _AlwaysCallsTool(), meter,
        tools={"mon_fails": mon_fails.tool_schema},
        max_turns=2, on_event=monitor.observe,
    )

    monitor.run(agent, "loop forever")  # must not raise

    exceptions = [i for i in monitor.issues if i["kind"] == "exception"]
    assert len(exceptions) == 1
    assert "MaxTurnsExceeded" in exceptions[0]["detail"]
    assert monitor.runs[-1]["ok"] is False


def test_observe_tolerates_missing_keys(tmp_path):
    """The monitor must never throw on a sparse event — its job is to not miss
    traces. A faulty observe() is swallowed by Agent._emit, so a raise here would
    silently drop this trace AND every later one in the turn."""
    monitor = SessionMonitor(log_dir=tmp_path)
    monitor.observe({"type": "tool_call"})    # no name / input
    monitor.observe({"type": "tool_result"})  # no name / content / is_error
    # reaching here without an exception is the assertion


def test_budget_exceeded_is_a_budget_issue_not_a_generic_exception(tmp_path):
    """A hard budget refusal is the project's headline failure mode, so run() tags
    it kind='budget' (distinct from any other exception) for the digest."""
    meter = CostMeter(str(tmp_path / "c.db"))
    meter.set_budget(0)  # any projected spend now trips the gate at turn 0
    monitor = SessionMonitor(log_dir=tmp_path)
    agent = Agent(_Priced(), meter, tools={})  # provider never reached

    monitor.run(agent, "spend money")

    assert [i["kind"] for i in monitor.issues] == ["budget"]
    assert "cap" in monitor.issues[0]["detail"].lower()
    assert monitor.runs[-1]["ok"] is False


def test_every_jsonl_record_has_a_wall_clock_timestamp(tmp_path):
    """Each event carries an absolute ISO timestamp so a stress run can be analysed
    as a latency/throughput timeline, not just relative tool durations."""
    from datetime import datetime

    meter = CostMeter(str(tmp_path / "c.db"))
    monitor = SessionMonitor(log_dir=tmp_path)
    agent = Agent(
        _OneToolThenDone(), meter,
        tools={"mon_fails": mon_fails.tool_schema},
        on_event=monitor.observe,
    )
    monitor.run(agent, "do it")

    lines = next(tmp_path.glob("demo-*.jsonl")).read_text().splitlines()
    assert lines
    for line in lines:
        rec = json.loads(line)
        assert "ts" in rec
        datetime.fromisoformat(rec["ts"])  # raises if not a valid ISO timestamp


def test_note_budget_records_each_warn_mark_once(tmp_path):
    """Crossing a €-warn mark records one budget issue; staying above it does not
    re-alarm (pins the prev<mark<=total boundary in _note_budget)."""
    monitor = SessionMonitor(log_dir=tmp_path)
    monitor._note_budget(5.0)    # below €10 — nothing
    monitor._note_budget(12.0)   # crosses €10
    monitor._note_budget(12.5)   # still above €10, no new mark — no duplicate

    budget = [i for i in monitor.issues if i["kind"] == "budget"]
    assert len(budget) == 1
    assert "€10" in budget[0]["detail"]


def test_summary_counts_issues(tmp_path):
    """summary() is the at-a-glance digest I read to find issues: it reports the
    tool-error and exception tallies."""
    meter = CostMeter(str(tmp_path / "c.db"))
    monitor = SessionMonitor(log_dir=tmp_path)
    agent = Agent(
        _AlwaysCallsTool(), meter,
        tools={"mon_fails": mon_fails.tool_schema},
        max_turns=2, on_event=monitor.observe,
    )
    monitor.run(agent, "loop")

    summary = monitor.summary()
    assert "1 exception" in summary
    # max_turns=2 dispatched mon_fails twice -> two is_error tool results
    assert "2 tool error" in summary


def test_issues_list_is_bounded(tmp_path):
    """A very long session can't grow the issue list unbounded; the tail is kept."""
    from palimpsest.monitor import _MAX_ISSUES

    monitor = SessionMonitor(log_dir=tmp_path)
    for i in range(_MAX_ISSUES + 100):
        monitor._add_issue({"kind": "tool_error", "tool": "t", "detail": str(i)})

    assert len(monitor.issues) == _MAX_ISSUES
    assert monitor.issues[-1]["detail"] == str(_MAX_ISSUES + 99)  # newest kept
    assert monitor.issues[0]["detail"] == str(100)               # oldest 100 dropped
    monitor.summary()  # still renders with a full list
