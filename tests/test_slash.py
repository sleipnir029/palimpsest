"""T27: slash command dispatcher. Offline, no app pilot needed — dispatch()
takes any object with an .exit() method, so a tiny fake stands in for the App."""

from __future__ import annotations

from palimpsest.tui.slash import SLASH_COMMANDS, dispatch


class _FakeApp:
    """Minimal stand-in: dispatch only ever calls app.exit() (for /quit)."""

    def __init__(self) -> None:
        self.exited = False

    def exit(self) -> None:
        self.exited = True


def test_help_lists_registered_commands():
    out = dispatch(_FakeApp(), "/help")
    # one line per registered command, each with its name
    for name in SLASH_COMMANDS:
        assert f"/{name}" in out
    assert "/help" in out and "/quit" in out
    # card requires one-line descriptions, not just names
    assert "list available commands" in out and "exit palimpsest" in out


def test_quit_exits_the_app():
    app = _FakeApp()
    dispatch(app, "/quit")
    assert app.exited is True


def test_unknown_command_returns_help_hint():
    # /parser is out of scope (T28 card) so it stays unknown; /budget is now wired.
    out = dispatch(_FakeApp(), "/parser docling")
    assert out == "unknown command: /parser. type /help for available commands."
