"""Tests for workspace versioning (dulwich auto-commit + per-turn tags).

Validates the safety net that makes bash's escape hatch acceptable: every
mutating action in the workspace is committed and undoable, while secrets and
bulk state are never committed.
"""

from __future__ import annotations

import pytest
from dulwich import porcelain
from dulwich.repo import Repo

from palimpsest import versioning


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    versioning.ensure_repo()
    return tmp_path


def _tracked(root):
    return {p.decode() if isinstance(p, bytes) else p for p in porcelain.ls_files(Repo(str(root)))}


def test_ensure_repo_creates_git_and_gitignore(ws):
    assert (ws / ".git").exists()
    assert "config.txt" in (ws / ".gitignore").read_text()


def test_checkpoint_commits_a_change(ws):
    (ws / "notes.md").write_text("hi", encoding="utf-8")
    sha = versioning.checkpoint("write notes")
    assert sha is not None
    assert "notes.md" in _tracked(ws)


def test_checkpoint_noop_when_unchanged(ws):
    (ws / "a.txt").write_text("x", encoding="utf-8")
    versioning.checkpoint("first")
    assert versioning.checkpoint("again") is None  # nothing new to commit


def test_secrets_and_bulk_state_never_committed(ws):
    (ws / "notes.md").write_text("real", encoding="utf-8")
    (ws / "config.txt").write_text("API_KEY=secret", encoding="utf-8")
    (ws / "palimpsest.db").write_text("ledger", encoding="utf-8")
    (ws / "store").mkdir()
    (ws / "store" / "g.ttl").write_text("triples", encoding="utf-8")
    versioning.checkpoint("turn")
    tracked = _tracked(ws)
    assert "notes.md" in tracked
    assert "config.txt" not in tracked
    assert "palimpsest.db" not in tracked
    assert not any(t.startswith("store/") for t in tracked)


def test_per_action_commits_accumulate(ws):
    (ws / "a.txt").write_text("1", encoding="utf-8")
    versioning.checkpoint("a")
    (ws / "b.txt").write_text("2", encoding="utf-8")
    versioning.checkpoint("b")
    repo = Repo(str(ws))
    history = list(repo.get_walker())
    assert len(history) == 2  # one commit per action


def test_checkpoint_captures_deletion(ws):
    f = ws / "gone.txt"
    f.write_text("x", encoding="utf-8")
    versioning.checkpoint("add")
    f.unlink()
    versioning.checkpoint("remove")
    assert "gone.txt" not in _tracked(ws)  # deletion was staged + committed


def test_tag_turn_marks_boundary_and_skips_noop(ws):
    (ws / "a.txt").write_text("x", encoding="utf-8")
    versioning.checkpoint("a")
    name = versioning.tag_turn()
    assert name and name.startswith("turn-")
    assert f"refs/tags/{name}".encode() in Repo(str(ws)).refs
    assert versioning.tag_turn() is None  # HEAD unmoved → no duplicate tag


def test_versioning_noop_without_repo(tmp_path, monkeypatch):
    # A workspace that was never ensure_repo'd: checkpoint/tag are silent no-ops
    # (this is what keeps the rest of the test-suite side-effect free).
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path / "bare"))
    assert versioning.checkpoint("x") is None
    assert versioning.tag_turn() is None


# --- integration: the agent loop drives checkpoint + tag --------------------

class _Resp:
    def __init__(self, tool_calls, text):
        self.usage, self.raw = {}, {"content": []}
        self.tool_calls, self.text = tool_calls, text


class _StubProvider:
    """Turn 1: call write_file. Turn 2: final answer (ends the turn)."""

    name = "stub"

    def __init__(self, ws):
        self.ws, self.n = ws, 0

    def complete(self, **kw):
        self.n += 1
        if self.n == 1:
            return _Resp(
                [{"id": "t1", "name": "write_file",
                  "input": {"path": str(self.ws / "out.md"), "content": "hello"}}],
                "",
            )
        return _Resp([], "done")


class _Meter:
    cap = 50.0

    def check_or_raise(self, projected_eur): ...
    def record_llm(self, *a, **k): ...
    def total_eur(self): return 0.0


def test_agent_run_checkpoints_per_action_and_tags_turn(ws):
    from palimpsest.agent import Agent

    agent = Agent(provider=_StubProvider(ws), cost_meter=_Meter(), tools={}, system_prompt="x")
    assert agent.run("make a file") == "done"
    assert (ws / "out.md").read_text() == "hello"  # the write tool actually ran

    repo = Repo(str(ws))
    assert len(list(repo.get_walker())) >= 1                      # per-action commit landed
    assert any(r.startswith(b"refs/tags/turn-") for r in repo.refs.keys())  # turn tagged
