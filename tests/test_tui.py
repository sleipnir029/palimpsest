"""T26 smoke test: PalimpsestApp mounts and the threaded reply path runs offline.

No network, no DEEPSEEK_API_KEY: a stub agent stands in for the real Agent. No
pytest-asyncio in the env, so the async Textual pilot is driven via asyncio.run().
This exercises the real path (submit → thread worker → call_from_thread →
re-enable input), not just construction.
"""

from __future__ import annotations

import asyncio

from textual.widgets import Input, RichLog, Static

from palimpsest.cost import CostMeter
from palimpsest.tui.app import PalimpsestApp


class _StubAgent:
    """Stand-in for Agent: no network. Records the message and bills the meter
    like the real Agent does, so the cost-bar update can be asserted."""

    def __init__(self, meter: CostMeter) -> None:
        self.meter = meter
        self.last: str | None = None

    def run(self, text: str) -> str:
        self.last = text
        self.meter.record_llm("stub", 0.01)
        return f"echo: {text}"


class _BoomAgent:
    """Raises on run() to exercise the worker error path."""

    last = None  # never set; asserts the slash path doesn't call it either

    def run(self, text: str) -> str:
        raise RuntimeError("kaboom")


class _ToolAgent:
    """Emits a tool-call + tool-result via the on_event observer before replying,
    standing in for the real Agent's per-dispatch events (T63). The app assigns
    `on_event`; the long result content lets the truncation be asserted."""

    LONG = "x" * 500  # longer than the TUI's truncation cap

    def __init__(self, meter: CostMeter) -> None:
        self.meter = meter
        self.on_event = None  # the app overwrites this with its callback

    def run(self, text: str) -> str:
        if self.on_event is not None:
            self.on_event(
                {"type": "tool_call", "name": "read_paper", "input": {"path": "papers/x.pdf"}}
            )
            self.on_event(
                {"type": "tool_result", "name": "read_paper", "content": self.LONG, "is_error": False}
            )
        self.meter.record_llm("stub", 0.01)
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
            log_text = "\n".join(strip.text for strip in app.query_one("#log", RichLog).lines)
            assert "hello" in log_text  # user line rendered
            assert "echo: hello" in log_text  # agent reply rendered
            # cost meter incremented (card requirement) — bar reflects the €0.01 bill
            assert "0.01" in str(app.query_one("#costbar", Static).render())

    asyncio.run(_drive())


def test_agent_error_surfaces_and_reenables_input(tmp_path):
    """A raising agent.run() becomes an `error:` line, not a crash; input recovers."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_BoomAgent(), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "hi"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.query_one("#prompt", Input).disabled is False
            log_text = "\n".join(strip.text for strip in app.query_one("#log", RichLog).lines)
            assert "error" in log_text and "kaboom" in log_text

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

            lines = [strip.text for strip in app.query_one("#log", RichLog).lines]
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
            self.meter = m
            self.on_event = None

        def run(self, text):
            if self.on_event is not None:
                self.on_event(
                    {"type": "tool_result", "name": "bash", "content": "error: nope", "is_error": True}
                )
            self.meter.record_llm("stub", 0.01)
            return "done"

    app = PalimpsestApp(agent=_ErrAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "do it"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            log_text = "\n".join(strip.text for strip in app.query_one("#log", RichLog).lines)
            assert "✗" in log_text
            assert "error: nope" in log_text

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
            log_text = "\n".join(strip.text for strip in app.query_one("#log", RichLog).lines)
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
            log_text = "\n".join(strip.text for strip in app.query_one("#log", RichLog).lines)
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
            log_text = "\n".join(strip.text for strip in app.query_one("#log", RichLog).lines)
            assert "bye" in log_text
            assert app._exit is True

    asyncio.run(_drive())
