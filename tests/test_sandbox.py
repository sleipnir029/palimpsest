"""Tests for the bash OS sandbox (src/palimpsest/sandbox.py + bash wiring).

Two layers:
- platform-independent logic (profile string, fail-closed, opt-out) — always run;
- real enforcement under the OS sandbox — `skipif`-gated on a mechanism being
  available, so the suite stays green on a box without sandbox-exec/bwrap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from palimpsest import sandbox
from palimpsest.policy import PolicyViolation
from palimpsest.tools.bash import bash

_NO_SANDBOX = sandbox.mechanism() is None


@pytest.fixture
def outside(tmp_path):
    """A target genuinely OUTSIDE the workspace AND outside any allowed temp dir.

    pytest's tmp_path lives under $TMPDIR, which the sandbox allows (mktemp etc.),
    so a temp sibling is NOT a valid 'escape' target — use a home sentinel, the
    real 'other place' the confinement protects. Cleaned up regardless of outcome.
    """
    p = Path.home() / ".palimpsest_sandbox_leakcheck"
    p.unlink(missing_ok=True)
    yield p
    p.unlink(missing_ok=True)


# --- profile generation (pure string, ungated) ------------------------------

def test_seatbelt_profile_confines_and_protects(tmp_path):
    prof = sandbox.seatbelt_profile(tmp_path)
    root = str(tmp_path.resolve())
    assert "(deny file-write*)" in prof
    assert f'(subpath "{root}")' in prof          # workspace is writable
    assert f'(subpath "{root}/store")' in prof    # ...but store/ re-denied
    assert f'(subpath "{root}/cache")' in prof
    assert r'(regex #"\.db$")' in prof            # ledger denied
    assert r'(regex #"\.key$")' in prof           # key material denied
    assert r'(regex #"/\.env$")' in prof          # secrets denied
    # the workspace-allow must come before the protected-deny (last match wins)
    assert prof.index(f'(subpath "{root}")') < prof.index(f'(subpath "{root}/store")')


def test_wrap_argv_shape_on_this_platform(tmp_path):
    if _NO_SANDBOX:
        with pytest.raises(PolicyViolation):
            sandbox.wrap("echo hi", tmp_path)
        return
    argv = sandbox.wrap("echo hi", tmp_path)
    assert argv[-3:] == ["/bin/bash", "-c", "echo hi"]
    assert argv[0] in ("/usr/bin/sandbox-exec", "bwrap")


# --- fail-closed / opt-out (ungated) ----------------------------------------

def test_bash_fails_closed_without_mechanism(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(sandbox, "mechanism", lambda: None)        # pretend none available
    monkeypatch.setattr("palimpsest.config.get_setting", lambda *a, **k: "on")
    with pytest.raises(PolicyViolation, match="sandbox required"):
        bash("echo hi")


def test_bash_optout_skips_sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    monkeypatch.setattr("palimpsest.config.get_setting", lambda *a, **k: "off")
    called = {}
    monkeypatch.setattr(sandbox, "wrap", lambda *a, **k: called.setdefault("wrapped", True) or [])
    out = bash("echo hi")
    assert "wrapped" not in called   # the sandbox was never invoked
    assert "hi" in out and "[exit 0]" in out


# --- real enforcement (gated on a mechanism existing) -----------------------

@pytest.mark.skipif(_NO_SANDBOX, reason="no OS sandbox mechanism on this platform")
def test_write_inside_workspace_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    out = bash("echo hi > inside.txt")
    assert (tmp_path / "inside.txt").read_text().strip() == "hi"
    assert "[exit 0]" in out


@pytest.mark.skipif(_NO_SANDBOX, reason="no OS sandbox mechanism on this platform")
def test_write_outside_workspace_blocked(tmp_path, monkeypatch, outside):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    out = bash(f'echo hi > "{outside}"')
    assert not outside.exists()
    assert "[exit 0]" not in out


@pytest.mark.skipif(_NO_SANDBOX, reason="no OS sandbox mechanism on this platform")
def test_rm_outside_workspace_blocked(tmp_path, monkeypatch, outside):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    outside.write_text("important", encoding="utf-8")  # created by the test, not bash
    bash(f'rm -f "{outside}"')
    assert outside.exists()  # the delete was refused by the OS


@pytest.mark.skipif(_NO_SANDBOX, reason="no OS sandbox mechanism on this platform")
def test_read_outside_workspace_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    out = bash("head -1 /etc/hosts > /dev/null && echo READ_OK")
    assert "READ_OK" in out and "[exit 0]" in out


@pytest.mark.skipif(_NO_SANDBOX, reason="no OS sandbox mechanism on this platform")
def test_symlink_target_outside_workspace_blocked(tmp_path, monkeypatch, outside):
    """The headline bypass: a symlink inside the workspace pointing OUT must not let
    a write escape — the OS resolves the link target's realpath."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    (tmp_path / "link").symlink_to(outside)
    bash('echo pwned > link')
    assert not outside.exists()               # the write did not follow the link out


@pytest.mark.skipif(_NO_SANDBOX, reason="no OS sandbox mechanism on this platform")
def test_child_process_cannot_drop_the_sandbox(tmp_path, monkeypatch, outside):
    """The property the whole approach rests on: descendants inherit the sandbox and
    cannot re-exec their way out (a nested sandbox-exec can only narrow, not widen)."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    bash(f"/usr/bin/sandbox-exec -p '(version 1)(allow default)' "
         f'/bin/bash -c "echo x > {outside}"')
    assert not outside.exists()               # nested re-exec didn't widen the fence


@pytest.mark.skipif(_NO_SANDBOX, reason="no OS sandbox mechanism on this platform")
def test_mktemp_in_systemp_works(tmp_path, monkeypatch):
    """$TMPDIR (/private/var/folders/... on macOS) must be writable, or mktemp and
    temp-respecting tools break under the sandbox."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    out = bash("mktemp >/dev/null && echo MKTEMP_OK")
    assert "MKTEMP_OK" in out and "[exit 0]" in out


@pytest.mark.skipif(_NO_SANDBOX, reason="no OS sandbox mechanism on this platform")
def test_timeout_kills_the_process_group(tmp_path, monkeypatch):
    """A timed-out sandboxed command is killed (group SIGKILL), not left orphaned."""
    import subprocess
    import time

    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    mark = "sleep 29.731"  # distinctive arg so pgrep can't match an unrelated sleep
    out = bash(mark, timeout=1)
    assert "timed out after 1" in out

    def _alive() -> bool:
        return subprocess.run(["pgrep", "-f", mark], capture_output=True).returncode == 0

    deadline = time.monotonic() + 2  # allow the SIGKILL a moment to land
    while _alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive()  # the whole group died — no orphaned sleep survived


@pytest.mark.skipif(_NO_SANDBOX, reason="no OS sandbox mechanism on this platform")
def test_db_write_inside_temp_still_blocked(tmp_path, monkeypatch):
    """N1 ($TMPDIR allow) must not widen the boundary: a *.db write is denied even in
    the allowed temp tree, exactly as inside the workspace."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    leak = Path("/private/tmp/palimpsest_sb_leak.db")
    leak.unlink(missing_ok=True)
    try:
        out = bash(f'echo x > "{leak}"')
        assert not leak.exists()
        assert "[exit 0]" not in out
    finally:
        leak.unlink(missing_ok=True)


@pytest.mark.skipif(_NO_SANDBOX, reason="no OS sandbox mechanism on this platform")
def test_protected_paths_blocked_inside_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    (tmp_path / "store").mkdir()
    assert "[exit 0]" not in bash("echo x > store/leak.ttl")  # provenance store
    assert not (tmp_path / "store" / "leak.ttl").exists()
    assert "[exit 0]" not in bash("echo x > ledger.db")        # ledger
    assert not (tmp_path / "ledger.db").exists()
    assert "[exit 0]" not in bash("echo SECRET=1 > .env")      # secrets
    assert not (tmp_path / ".env").exists()
