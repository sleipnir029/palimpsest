"""Tests for the constrained-autonomy policy + the guarded write/edit/bash tools.

The policy is the thesis's enforcement boundary, so these assert the invariants
hold *in code*: the agent can act inside its workspace but is physically refused
outside it, and the pipeline-managed graph/cache/ledger stay off-limits to direct
edits even inside the workspace.
"""

from __future__ import annotations

import pytest

from palimpsest import policy, sandbox
from palimpsest.policy import PolicyViolation, assert_bash_allowed, assert_writable
from palimpsest.tools.bash import bash

_NO_SANDBOX = sandbox.mechanism() is None  # gate enforcement tests off unsupported CI
from palimpsest.tools.edit_file import edit_file
from palimpsest.tools.write_file import write_file


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """Point the workspace root at an isolated temp dir for each test."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    return tmp_path


# --- assert_writable --------------------------------------------------------

def test_allows_file_inside_workspace(ws):
    assert assert_writable(str(ws / "notes.md")) == (ws / "notes.md").resolve()


def test_denies_outside_workspace(ws):
    with pytest.raises(PolicyViolation, match="outside workspace"):
        assert_writable(str(ws.parent / "engine.py"))


def test_denies_dotdot_escape(ws):
    # resolve() collapses the .. so the escape is caught, not allowed through.
    with pytest.raises(PolicyViolation, match="outside workspace"):
        assert_writable(str(ws / ".." / "secrets.txt"))


def test_denies_graph_store_even_inside_workspace(ws):
    with pytest.raises(PolicyViolation, match="protected"):
        assert_writable(str(ws / "store" / "data.ttl"))


def test_denies_cache_and_ledger_and_config(ws):
    for bad in ("cache/mineru.json", "palimpsest.db", "config.txt"):
        with pytest.raises(PolicyViolation, match="protected"):
            assert_writable(str(ws / bad))


def test_denies_prefix_collision_sibling(ws):
    # /tmp/.../wsNNN-evil must NOT count as inside /tmp/.../wsNNN (the startswith bug).
    sibling = ws.parent / (ws.name + "-evil")
    with pytest.raises(PolicyViolation, match="outside workspace"):
        assert_writable(str(sibling / "f.txt"))


def test_denies_symlink_escape(ws, tmp_path):
    # A symlink inside the workspace pointing out resolves out → denied.
    outside = tmp_path.parent / "outside_dir"
    outside.mkdir(exist_ok=True)
    link = ws / "escape"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PolicyViolation, match="outside workspace"):
        assert_writable(str(link / "f.txt"))


def test_ledger_rename_is_a_known_gap(ws):
    # Documents B3: protection is name-coupled, so a ledger renamed off `.db`
    # slips through. Asserts the current (imperfect) behavior so a future fix
    # (derive protected paths from config) flips this test deliberately.
    assert assert_writable(str(ws / "ledger.sqlite"))  # allowed today — known gap


# --- assert_bash_allowed ----------------------------------------------------

def test_bash_blocks_unmetered_spend():
    for bad in ("python -m palimpsest demo x.pdf", "runpodctl get pod", "runpod create"):
        with pytest.raises(PolicyViolation, match="un-metered spend"):
            assert_bash_allowed(bad)


def test_bash_deny_list_resists_whitespace_evasion():
    with pytest.raises(PolicyViolation):
        assert_bash_allowed("python  -m   palimpsest demo x.pdf")


def test_bash_allows_local_dev_commands():
    for ok in ("pytest -q", "git status", "ls -la", "marimo edit nb.py"):
        assert_bash_allowed(ok) is None  # no raise


# --- write_file -------------------------------------------------------------

def test_write_file_creates_nested_path(ws):
    msg = write_file(str(ws / "analysis" / "out.md"), "# results")
    assert (ws / "analysis" / "out.md").read_text() == "# results"
    assert "wrote 9 chars" in msg


def test_write_file_refused_outside_workspace(ws):
    with pytest.raises(PolicyViolation):
        write_file(str(ws.parent / "evil.py"), "x")


def test_write_file_refused_for_protected(ws):
    with pytest.raises(PolicyViolation):
        write_file(str(ws / "store" / "g.ttl"), "x")


# --- edit_file --------------------------------------------------------------

def test_edit_file_unique_replace(ws):
    f = ws / "a.txt"
    f.write_text("alpha beta gamma", encoding="utf-8")
    edit_file(str(f), "beta", "BETA")
    assert f.read_text() == "alpha BETA gamma"


def test_edit_file_reports_missing_and_ambiguous(ws):
    f = ws / "b.txt"
    f.write_text("x x x", encoding="utf-8")
    assert "not found" in edit_file(str(f), "zzz", "q")
    assert "occurs 3 times" in edit_file(str(f), "x", "y")


# --- bash -------------------------------------------------------------------

def test_bash_runs_in_workspace_cwd(ws, monkeypatch):
    # cwd-pinning is orthogonal to the sandbox; force the fence off so this asserts
    # the plumbing deterministically on platforms with no sandbox mechanism.
    monkeypatch.setattr("palimpsest.config.get_setting", lambda *a, **k: "off")
    (ws / "marker.txt").write_text("", encoding="utf-8")
    out = bash("ls")
    assert "marker.txt" in out and "[exit 0]" in out


def test_bash_refuses_unmetered_spend(ws):
    with pytest.raises(PolicyViolation):
        bash("python -m palimpsest demo papers/x.pdf")


@pytest.mark.skipif(_NO_SANDBOX, reason="no OS sandbox mechanism on this platform")
def test_bash_writes_are_confined_to_workspace(ws):
    # The new contract: with the sandbox on (default), a shell write OUTSIDE the
    # workspace is refused by the OS — the escape hatch can no longer escape. Target
    # a home sentinel (not a temp sibling — $TMPDIR is an allowed scratch area).
    import pathlib

    outside = pathlib.Path.home() / ".palimpsest_sandbox_leakcheck_policy"
    outside.unlink(missing_ok=True)
    try:
        out = bash(f'echo escaped > "{outside}"')
        assert not outside.exists()  # the write never landed
        assert "[exit 0]" not in out
    finally:
        outside.unlink(missing_ok=True)  # and the command reported failure


def test_bash_unconfined_when_sandbox_off(ws, tmp_path, monkeypatch):
    # The documented override: `/config set bash_sandbox off` restores the raw,
    # unfenced escape hatch (the human's responsibility).
    monkeypatch.setattr("palimpsest.config.get_setting", lambda *a, **k: "off")
    outside = tmp_path.parent / "bash_optout.txt"
    bash(f'echo escaped > "{outside}"')
    assert outside.exists()
    outside.unlink()
