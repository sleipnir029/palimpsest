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
    # Reset versioning's per-process tag state so each test's repo starts clean.
    # Without this, identical commits across tests collide on sha (same tree +
    # message + second + no parent) and tag_turn's `_last_tagged` skip suppresses
    # a turn tag, making turn-dependent tests order-sensitive.
    monkeypatch.setattr(versioning, "_last_tagged", None)
    monkeypatch.setattr(versioning, "_turn", 0)
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


# --- /undo: single-step revert to the previous turn (T64) -------------------

def _turn(ws, writes=(), deletes=(), msg="turn"):
    """Simulate one agent turn: apply file changes, checkpoint, tag the turn."""
    for name, content in writes:
        (ws / name).write_text(content, encoding="utf-8")
    for name in deletes:
        (ws / name).unlink()
    versioning.checkpoint(msg)
    return versioning.tag_turn()


def test_undo_removes_files_added_by_last_turn(ws):
    target = _turn(ws, writes=[("a.txt", "one")])   # turn 1 — the state we revert TO
    _turn(ws, writes=[("b.txt", "two")])            # turn 2 — the turn we undo
    r = versioning.undo_last_turn()
    assert r.undone is True
    assert r.target_tag == target
    assert not (ws / "b.txt").exists()              # added file physically gone
    assert (ws / "a.txt").read_text() == "one"      # prior-turn file untouched
    assert "b.txt" in r.changed


def test_undo_restores_modified_file(ws):
    _turn(ws, writes=[("a.txt", "v1")])
    _turn(ws, writes=[("a.txt", "v2")])
    r = versioning.undo_last_turn()
    assert r.undone is True
    assert (ws / "a.txt").read_text() == "v1"
    assert "a.txt" in r.changed


def test_undo_restores_deleted_file(ws):
    _turn(ws, writes=[("a.txt", "keep me"), ("b.txt", "stay")])
    _turn(ws, deletes=["a.txt"])
    r = versioning.undo_last_turn()
    assert r.undone is True
    assert (ws / "a.txt").read_text() == "keep me"


def test_undo_is_append_only(ws):
    _turn(ws, writes=[("a.txt", "one")])
    _turn(ws, writes=[("b.txt", "two")])
    repo = Repo(str(ws))
    head_before = repo.head()
    n_before = len(list(repo.get_walker()))
    tags_before = {x for x in repo.refs.keys() if x.startswith(b"refs/tags/turn-")}

    r = versioning.undo_last_turn()

    repo = Repo(str(ws))
    assert len(list(repo.get_walker())) == n_before + 1   # a NEW commit, not a rewrite
    assert repo[repo.head()].parents == [head_before]     # revert sits ON TOP of HEAD
    assert r.revert_sha == repo.head().decode()
    after = {x for x in repo.refs.keys() if x.startswith(b"refs/tags/turn-")}
    assert tags_before <= after                           # turn tags preserved


def test_undo_first_turn_refuses(ws):
    _turn(ws, writes=[("a.txt", "one")])   # only one turn — no prior turn-state exists
    n_before = len(list(Repo(str(ws)).get_walker()))
    r = versioning.undo_last_turn()
    assert r.undone is False
    assert "first turn" in r.detail.lower()
    assert (ws / "a.txt").read_text() == "one"                   # nothing destroyed
    assert len(list(Repo(str(ws)).get_walker())) == n_before     # no commit added


def test_undo_discards_incomplete_untagged_turn(ws):
    # A turn that committed work but never tagged a boundary (e.g. MaxTurnsExceeded
    # skips tag_turn): /undo should discard it back to the last *completed* turn,
    # not revert two turns at once.
    target = _turn(ws, writes=[("a.txt", "one")])      # completed, tagged
    (ws / "b.txt").write_text("partial", encoding="utf-8")
    versioning.checkpoint("write_file: b.txt")          # committed, NOT tagged
    r = versioning.undo_last_turn()
    assert r.undone is True
    assert r.target_tag == target                       # back to the last completed turn
    assert not (ws / "b.txt").exists()                  # incomplete work discarded
    assert (ws / "a.txt").read_text() == "one"          # completed turn preserved
    assert "b.txt" in r.changed


def test_undo_preserves_untracked_files(ws):
    # No data loss: an untracked, non-ignored file the human dropped in the
    # workspace must survive undo (it is in neither tree, so reset must not touch it).
    _turn(ws, writes=[("a.txt", "one")])
    _turn(ws, writes=[("b.txt", "two")])
    (ws / "scratch.txt").write_text("mine", encoding="utf-8")  # untracked
    r = versioning.undo_last_turn()
    assert r.undone is True
    assert not (ws / "b.txt").exists()                    # undone turn's file gone
    assert (ws / "scratch.txt").read_text() == "mine"     # untracked file preserved


def test_undo_without_repo_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path / "bare"))
    r = versioning.undo_last_turn()
    assert r.undone is False


def test_undo_twice_is_idempotent(ws):
    _turn(ws, writes=[("a.txt", "one")])
    _turn(ws, writes=[("b.txt", "two")])
    versioning.undo_last_turn()
    n_after_first = len(list(Repo(str(ws)).get_walker()))
    r2 = versioning.undo_last_turn()        # already at target → no new commit
    assert r2.undone is True
    assert r2.revert_sha is None
    assert len(list(Repo(str(ws)).get_walker())) == n_after_first


def test_undo_raises_if_reset_moves_head(ws, monkeypatch):
    # Append-only invariant guard: if a future dulwich ever made porcelain.reset
    # move HEAD, undo must fail loudly rather than silently rewind the branch.
    _turn(ws, writes=[("a.txt", "one")])
    _turn(ws, writes=[("b.txt", "two")])
    real_reset = versioning.porcelain.reset

    def reset_then_rewind(repo, mode, treeish):
        real_reset(repo, mode, treeish)
        repo.refs[b"HEAD"] = repo[repo.head()].parents[0]  # simulate a HEAD rewind

    monkeypatch.setattr(versioning.porcelain, "reset", reset_then_rewind)
    with pytest.raises(RuntimeError, match="append-only invariant broken"):
        versioning.undo_last_turn()


def test_recent_history_lists_commits_with_turn_tags(ws):
    (ws / "a.txt").write_text("1", encoding="utf-8")
    versioning.checkpoint("first checkpoint")
    tag = versioning.tag_turn()                       # tags HEAD as a turn boundary
    (ws / "b.txt").write_text("2", encoding="utf-8")
    versioning.checkpoint("second checkpoint")

    hist = versioning.recent_history(10)
    assert [h["title"] for h in hist] == ["second checkpoint", "first checkpoint"]  # newest first
    # the tagged commit carries its turn tag; the later untagged one does not
    by_title = {h["title"]: h for h in hist}
    assert by_title["first checkpoint"]["tag"] == tag
    assert by_title["second checkpoint"]["tag"] is None
    assert all(len(h["sha"]) == 8 for h in hist)


def test_recent_history_honors_limit_and_empty_repo(ws, tmp_path, monkeypatch):
    for i in range(5):
        (ws / f"f{i}.txt").write_text(str(i), encoding="utf-8")
        versioning.checkpoint(f"c{i}")
    assert len(versioning.recent_history(3)) == 3   # capped

    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path / "bare"))  # never ensure_repo'd
    assert versioning.recent_history() == []        # no repo → empty, not an error
