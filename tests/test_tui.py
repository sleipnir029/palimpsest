"""T26 smoke test: PalimpsestApp mounts and the threaded reply path runs offline.

No network, no DEEPSEEK_API_KEY: a stub agent stands in for the real Agent. No
pytest-asyncio in the env, so the async Textual pilot is driven via asyncio.run().
This exercises the real path (submit → thread worker → call_from_thread →
re-enable input), not just construction.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Input, Static

from palimpsest.cost import CostMeter
from palimpsest.tui.app import PalimpsestApp


def _text(app: PalimpsestApp) -> str:
    """The on-screen transcript as plain text — the stable seam for assertions.

    The view is a tree of per-message widgets (Scriptorium rebuild); the app mirrors
    every appended message into ``app.transcript`` as (role, text) in order, so tests
    assert content + ordering without reaching into widget internals."""
    return "\n".join(t for _role, t in app.transcript)


@pytest.fixture(autouse=True)
def _isolate_workspace(tmp_path, monkeypatch):
    """Point the workspace at a throwaway dir so the app's SessionMonitor writes its
    demo log into tmp, never the real ./workspace/.palimpsest (test isolation —
    mirrors test_session/test_versioning). Without this, constructing PalimpsestApp
    pollutes the real workspace and can trip a live monitor with a fixture event."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))


class _StubAgent:
    """Stand-in for Agent: no network. Records the message and bills the meter
    like the real Agent does, so the cost-bar update can be asserted."""

    def __init__(self, meter: CostMeter) -> None:
        # cost_meter mirrors the real Agent's attribute — monitor.run() reads it to
        # meter the per-turn euro delta.
        self.cost_meter = meter
        self.last: str | None = None

    def run(self, text: str) -> str:
        self.last = text
        self.cost_meter.record_llm("stub", 0.01)
        return f"echo: {text}"


class _BoomAgent:
    """Raises on run() to exercise the worker error path."""

    last = None  # never set; asserts the slash path doesn't call it either

    def __init__(self, meter: CostMeter) -> None:
        self.cost_meter = meter  # monitor.run reads it before invoking run()

    def run(self, text: str) -> str:
        raise RuntimeError("kaboom")


class _ToolAgent:
    """Emits a tool-call + tool-result via the on_event observer before replying,
    standing in for the real Agent's per-dispatch events (T63). The app assigns
    `on_event`; the long result content lets the truncation be asserted."""

    LONG = "x" * 500  # longer than the TUI's truncation cap

    def __init__(self, meter: CostMeter) -> None:
        self.cost_meter = meter
        self.on_event = None  # the app overwrites this with its callback

    def run(self, text: str) -> str:
        if self.on_event is not None:
            self.on_event(
                {"type": "tool_call", "name": "read_paper", "input": {"path": "papers/x.pdf"}}
            )
            self.on_event(
                {"type": "tool_result", "name": "read_paper", "content": self.LONG, "is_error": False}
            )
        self.cost_meter.record_llm("stub", 0.01)
        return "final reply"


def test_app_smoke_reply_path(tmp_path):
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "hello"
            await pilot.press("enter")
            await app.workers.wait_for_complete()  # let the thread worker finish
            await pilot.pause()  # let the call_from_thread callback settle

            assert agent.last == "hello"  # agent was actually invoked
            prompt = app.query_one("#prompt", Input)
            assert prompt.disabled is False  # re-enabled after reply
            log_text = _text(app)
            assert "hello" in log_text  # user line rendered
            assert "echo: hello" in log_text  # agent reply rendered
            # cost meter incremented (card requirement) — bar reflects the €0.01 bill
            assert "0.01" in str(app.query_one("#status", Static).render())

    asyncio.run(_drive())


def test_tui_records_per_turn_cost(tmp_path):
    """The TUI routes the turn through the monitor so each turn's euro delta is
    recorded (previously the TUI called agent.run directly and logged no turn cost)."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "hello"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

    asyncio.run(_drive())

    assert app.monitor.runs, "no per-turn cost recorded"
    assert app.monitor.runs[-1]["prompt"] == "hello"
    assert app.monitor.runs[-1]["cost_eur"] == 0.01  # _StubAgent bills €0.01


def test_agent_error_surfaces_and_reenables_input(tmp_path):
    """A raising agent.run() surfaces as an `[error]` line (from monitor.run), not a
    crash; input recovers and the monitor records the failed turn."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_BoomAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "hi"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.query_one("#prompt", Input).disabled is False
            log_text = _text(app)
            assert "error" in log_text and "kaboom" in log_text
            # the TUI path records the failed turn through the monitor
            assert app.monitor.runs[-1]["ok"] is False
            assert any(i["kind"] == "exception" for i in app.monitor.issues)

    asyncio.run(_drive())


def test_tool_trace_streams_before_reply(tmp_path):
    """T63: tool calls + results stream into the log live, before the final reply,
    and long results are truncated."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _ToolAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "read the paper"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            lines = [t for _role, t in app.transcript]
            log_text = "\n".join(lines)
            # tool-call line rendered
            assert "→ read_paper" in log_text
            assert "papers/x.pdf" in log_text
            # the tool-call line appears BEFORE the final reply line (ordering)
            call_idx = next(i for i, t in enumerate(lines) if "→ read_paper" in t)
            reply_idx = next(i for i, t in enumerate(lines) if "final reply" in t)
            assert call_idx < reply_idx
            # long result truncated: ellipsis present, full 500-char blob absent
            assert "…" in log_text
            assert _ToolAgent.LONG not in log_text

    asyncio.run(_drive())


def test_tool_error_result_renders_failure_marker(tmp_path):
    """T63: a tool_result with is_error=True renders the ✗ marker, not ←."""
    meter = CostMeter(str(tmp_path / "t.db"))

    class _ErrAgent:
        def __init__(self, m):
            self.cost_meter = m
            self.on_event = None

        def run(self, text):
            if self.on_event is not None:
                self.on_event(
                    {"type": "tool_result", "name": "bash", "content": "error: nope", "is_error": True}
                )
            self.cost_meter.record_llm("stub", 0.01)
            return "done"

    app = PalimpsestApp(agent=_ErrAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "do it"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            log_text = _text(app)
            assert "✗" in log_text
            assert "error: nope" in log_text

    asyncio.run(_drive())


def test_escape_requests_cancellation_when_in_flight(tmp_path):
    """T65: the app shares one cancel event with the agent; Esc sets it only while a
    turn is in flight (input disabled), so an idle Esc can't poison the next run."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            # the agent checks the very event the app sets (one shared Event)
            assert app.agent.cancel_event is app.cancel_event

            # nothing in flight (input enabled) → Esc is a no-op
            await pilot.press("escape")
            assert app.cancel_event.is_set() is False

            # simulate a turn in flight, then Esc requests cancellation
            app.query_one("#prompt", Input).disabled = True
            await pilot.press("escape")
            assert app.cancel_event.is_set() is True
            log_text = _text(app)
            assert "cancel" in log_text.lower()

    asyncio.run(_drive())


def test_submit_clears_stale_cancel_before_running(tmp_path):
    """T65 race-avoidance: the app clears a stale cancel on the main thread at submit
    (before arming the in-flight guard), so a leftover Esc can't abort the new turn."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.cancel_event.set()  # stale, as if left set from before
            app.query_one("#prompt", Input).value = "hello"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.cancel_event.is_set() is False  # cleared at submit
            assert agent.last == "hello"  # the run proceeded normally

    asyncio.run(_drive())


def test_slash_command_dispatched(tmp_path):
    """A `/`-prefixed line goes to the slash dispatcher, never to the agent.
    `/parser` is out of scope (T28 card), so it stays an unknown command."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "/parser docling"
            await pilot.press("enter")
            await pilot.pause()
            assert agent.last is None  # agent not called for slash commands
            log_text = _text(app)
            assert "unknown command: /parser" in log_text

    asyncio.run(_drive())


def test_slash_help_lists_commands_in_app(tmp_path):
    """`/help` renders the command list into the log (card's manual step)."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "/help"
            await pilot.press("enter")
            await pilot.pause()
            assert agent.last is None
            log_text = _text(app)
            assert "/help" in log_text and "/quit" in log_text

    asyncio.run(_drive())


def test_slash_quit_exits_the_app(tmp_path):
    """`/quit` exits the real app — and the write-after-exit("bye") doesn't crash."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "/quit"
            await pilot.press("enter")
            await pilot.pause()
            assert agent.last is None  # agent not called
            # "bye" rendered == the write-after-exit() ran without crashing,
            # and _exit is set == app.exit() was actually invoked by the handler
            log_text = _text(app)
            assert "bye" in log_text
            assert app._exit is True

    asyncio.run(_drive())
