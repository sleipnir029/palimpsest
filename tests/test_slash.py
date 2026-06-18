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


def test_undo_command_reverts_last_turn(tmp_path, monkeypatch):
    # /undo (T64) reads the workspace via PALIMPSEST_WORKSPACE, not the app — so a
    # bare fake app is enough. Drive two turns, then undo the last one.
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    from palimpsest import versioning

    versioning.ensure_repo()
    (tmp_path / "a.txt").write_text("one"); versioning.checkpoint("t1"); versioning.tag_turn()
    (tmp_path / "b.txt").write_text("two"); versioning.checkpoint("t2"); versioning.tag_turn()

    out = dispatch(_FakeApp(), "/undo")
    assert not (tmp_path / "b.txt").exists()   # the last turn's file is gone
    assert "b.txt" in out                      # and the report names it
