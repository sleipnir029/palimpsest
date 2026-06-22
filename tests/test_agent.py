"""T06 tests. These call the real Anthropic API and cost a few cents.

Each test uses a throwaway SQLite ledger (tmp_path) so the budget starts fresh.
"""

import os
import threading

import pytest
from dotenv import load_dotenv

from palimpsest.agent import Agent, MaxTurnsExceeded
from palimpsest.cost import CostMeter
from palimpsest.providers import AnthropicProvider
from palimpsest.providers.anthropic import LLMResponse
from palimpsest.tools import register

load_dotenv()


@pytest.fixture(autouse=True)
def _isolate_workspace(tmp_path, monkeypatch):
    """Isolate the workspace so a constructed Agent's SessionLog (T66) and versioning
    write into tmp (no .git there → no-ops), never the real ./workspace transcript.
    Without this, every agent.run() here pollutes the real session.jsonl."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))


_skip_no_key = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set (.env missing or empty)",
)


# A tool that always raises, used to drive the loop to max_turns.
@register("always_fails", {
    "description": "Always raises an error. Call this to attempt the task.",
    "input_schema": {"type": "object", "properties": {}},
})
def always_fails() -> str:
    raise RuntimeError("boom")


@pytest.mark.live
@_skip_no_key
def test_no_tools(tmp_path):
    meter = CostMeter(str(tmp_path / "c.db"))
    agent = Agent(AnthropicProvider(), meter, tools={})
    out = agent.run("Reply with exactly 'pong' and nothing else.")
    assert out.strip() == "pong"

    n_llm = meter.conn.execute(
        "SELECT COUNT(*) FROM cost_ledger WHERE kind = 'llm'"
    ).fetchone()[0]
    assert n_llm == 1


@pytest.mark.live
@_skip_no_key
def test_cache_hit_on_second_run(tmp_path):
    meter = CostMeter(str(tmp_path / "c.db"))
    # Cache minimum is 1024 tokens; pad the stable system prefix well past it.
    system = "You are a meticulous extraction agent. " * 400  # ~2800 tokens
    agent = Agent(AnthropicProvider(), meter, tools={}, system_prompt=system)

    agent.run("Reply with exactly 'one'.")
    agent.run("Reply with exactly 'two'.")

    cache_read = agent.last_usage["cache_read_input_tokens"]
    print(f"\ncache_read = {cache_read}")
    assert cache_read > 0


class _AlwaysCallsToolProvider:
    """Stub provider: every turn emits a tool_call, so the loop never finishes.

    The max_turns bound is pure control flow, so this is tested deterministically
    (and for free) rather than hoping the live model keeps calling a failing tool.
    """

    name = "stub"

    def complete(self, system, messages, tools, cache_breakpoints, on_text=None):
        # on_text is accepted (streaming interface) but unused: a tool-only turn has
        # no text to stream, so the loop sees only tool_call/tool_result events.
        call = {"id": "t1", "name": "always_fails", "input": {}}
        return LLMResponse(
            text="",
            tool_calls=[call],
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            raw={"content": [{"type": "tool_use", **call}]},
        )


def test_max_turns(tmp_path):
    meter = CostMeter(str(tmp_path / "c.db"))
    agent = Agent(
        _AlwaysCallsToolProvider(),
        meter,
        tools={"always_fails": always_fails.tool_schema},
        max_turns=3,
    )
    with pytest.raises(MaxTurnsExceeded):
        agent.run("Do the task.")


def test_on_event_emits_call_then_result(tmp_path):
    """T63: the loop fires a tool_call event then a tool_result event per dispatch,
    the result carries content + is_error (always_fails raises → is_error=True)."""
    meter = CostMeter(str(tmp_path / "c.db"))
    events: list[dict] = []
    agent = Agent(
        _AlwaysCallsToolProvider(),
        meter,
        tools={"always_fails": always_fails.tool_schema},
        max_turns=1,
        on_event=events.append,
    )
    with pytest.raises(MaxTurnsExceeded):
        agent.run("Do the task.")

    assert [e["type"] for e in events] == ["tool_call", "tool_result"]
    call, result = events
    assert call["name"] == "always_fails" and call["input"] == {}
    assert result["name"] == "always_fails"
    assert result["is_error"] is True
    assert "boom" in result["content"]  # the tool's RuntimeError, surfaced


def test_faulty_observer_does_not_break_the_turn(tmp_path):
    """T63 invariant: a raising on_event must not change the loop — the turn still
    proceeds to MaxTurnsExceeded, not the observer's RuntimeError."""
    meter = CostMeter(str(tmp_path / "c.db"))

    def boom(_event):
        raise RuntimeError("observer exploded")

    agent = Agent(
        _AlwaysCallsToolProvider(),
        meter,
        tools={"always_fails": always_fails.tool_schema},
        max_turns=1,
        on_event=boom,
    )
    with pytest.raises(MaxTurnsExceeded):  # not RuntimeError("observer exploded")
        agent.run("Do the task.")


class _CancelsOnFirstCall(_AlwaysCallsToolProvider):
    """Loops forever like the parent, but sets a cancel event the first time it is
    called — simulating the supervisor hitting Esc while a turn is in flight."""

    def __init__(self, cancel: threading.Event) -> None:
        self._cancel = cancel
        self.calls = 0

    def complete(self, system, messages, tools, cache_breakpoints):
        self.calls += 1
        self._cancel.set()
        return super().complete(system, messages, tools, cache_breakpoints)


def test_cancel_event_exits_before_max_turns(tmp_path):
    """T65: a cancel event set mid-run ends run() at the NEXT turn boundary with a
    'cancelled' note instead of looping to MaxTurnsExceeded — and no further paid
    call is made once the flag is seen (stops a runaway before more spend)."""
    meter = CostMeter(str(tmp_path / "c.db"))
    cancel = threading.Event()
    provider = _CancelsOnFirstCall(cancel)
    agent = Agent(
        provider,
        meter,
        tools={"always_fails": always_fails.tool_schema},
        max_turns=40,
        cancel_event=cancel,
    )
    out = agent.run("Do the task.")  # must NOT raise MaxTurnsExceeded
    assert "cancel" in out.lower()
    assert provider.calls == 1  # turn 1's boundary check returned before a 2nd call


def test_streaming_cancel_returns_cancelled_note(tmp_path):
    """#3: Esc mid-reply (cancel set) makes Agent._stream_delta raise StreamCancelled
    when a delta arrives; run() catches it and returns a [cancelled] note, no extra turn."""
    meter = CostMeter(str(tmp_path / "c.db"))
    cancel = threading.Event()
    cancel.set()  # the user already pressed Esc

    class _StreamingProvider:
        name = "stub"

        def complete(self, system, messages, tools, cache_breakpoints, on_text=None, **kw):
            if on_text is not None:
                on_text("partial")  # _stream_delta sees the cancel flag → raises
            raise AssertionError("loop must stop before the response is processed")

    agent = Agent(
        _StreamingProvider(), meter, tools={},
        on_event=lambda _e: None,  # enables streaming (on_text is passed)
        cancel_event=cancel,
    )
    out = agent.run("hi")
    assert "cancel" in out.lower()


def test_preset_cancel_returns_immediately_without_a_paid_call(tmp_path):
    """The caller owns the cancel flag's lifecycle — run() does NOT auto-clear it
    (that would race the cross-thread set, T65). So an already-set event makes run()
    return the cancelled note at turn 0, before the provider is ever called."""
    meter = CostMeter(str(tmp_path / "c.db"))
    cancel = threading.Event()
    cancel.set()  # supervisor requested a stop before this run even begins

    class _NeverCalled:
        name = "stub"

        def complete(self, system, messages, tools, cache_breakpoints):
            raise AssertionError("provider must not be called when cancel is preset")

    agent = Agent(_NeverCalled(), meter, tools={}, cancel_event=cancel)
    out = agent.run("hi")
    assert "cancel" in out.lower()
