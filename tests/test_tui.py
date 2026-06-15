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


def test_slash_command_stubbed(tmp_path):
    """A `/`-prefixed line is stubbed (T27), never sent to the agent."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "/budget 100"
            await pilot.press("enter")
            await pilot.pause()
            assert agent.last is None  # agent not called for slash commands
            log_text = "\n".join(strip.text for strip in app.query_one("#log", RichLog).lines)
            assert "T27" in log_text

    asyncio.run(_drive())
