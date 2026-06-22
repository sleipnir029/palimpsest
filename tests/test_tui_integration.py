"""Integration smoke: drive the REAL PalimpsestApp through its slash commands and
assert the *wiring* holds together — the footer reflects /use + /budget, the topbar
+ theme reflect /theme, and /resume restores history. Unit tests cover the handlers
in isolation (via a fake app); this proves the handlers, the footer/topbar, the
settings db, and the theme registry actually integrate in one live app instance.

Offline: a stub agent stands in for the LLM (no network). The real end-to-end LLM
call is a manual smoke (needs a key + budget) — see the hardening run in the PR.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Input, Static

from palimpsest.config import get_setting
from palimpsest.cost import CostMeter
from palimpsest.tui.app import PalimpsestApp


@pytest.fixture(autouse=True)
def _isolate_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))


class _StubAgent:
    """No network. Carries the attributes the app + /resume touch."""

    def __init__(self, meter: CostMeter) -> None:
        self.cost_meter = meter
        self.last = None
        self.messages: list = []
        self.on_event = None
        self.cancel_event = None
        self.session = type("_S", (), {"load": lambda _s, limit=None: [
            {"role": "user", "content": "earlier question"},
            {"role": "assistant", "content": [{"type": "text", "text": "earlier answer"}]},
        ]})()

    def run(self, text: str) -> str:
        self.last = text
        self.cost_meter.record_llm("stub", 0.01)
        return "ok"


def test_tui_commands_integrate(tmp_path):
    db = str(tmp_path / "t.db")
    meter = CostMeter(db)
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test(size=(94, 30)) as pilot:
            async def cmd(line: str) -> None:
                app.query_one("#prompt", Input).value = line
                await pilot.press("enter")
                await pilot.pause()

            footer = lambda: str(app.query_one("#status", Static).render())  # noqa: E731
            topbar = lambda: str(app.query_one("#topbar", Static).render())  # noqa: E731

            await cmd("/use extraction gemini")
            assert "extract:gemini" in footer()
            assert get_setting("extraction_model", db_path=db) == "gemini"

            await cmd("/use parser docling")
            assert "parse:docling" in footer()

            await cmd("/theme oxide")
            assert app.theme == "oxide"
            assert "oxide" in topbar()
            assert get_setting("ui_theme", db_path=db) == "oxide"

            await cmd("/budget 75")
            assert app.cost_meter.cap == 75
            assert "€75" in footer()

            await cmd("/resume")
            assert len(app.agent.messages) == 2  # prior context restored
            transcript = "\n".join(t for _role, t in app.transcript)
            assert "earlier question" in transcript

    asyncio.run(_drive())
