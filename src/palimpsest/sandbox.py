"""OS-level sandbox for the ``bash`` tool — confine file writes to the workspace.

``bash`` is the agent's escape hatch: a real shell that can use absolute paths,
``cd``, and ``rm``. A string guard can't fence that, so we push the boundary into
the OS. Every command runs under macOS Seatbelt (``sandbox-exec``) — or Linux
``bwrap`` where present — with a profile that allows **reads, exec, and network**
but **denies all file writes except under the workspace**, and re-denies the
pipeline-managed paths (``store/``, ``cache/``, the ``*.db`` ledger, secrets) even
there, mirroring what ``write_file``/``edit_file`` already refuse.

Reads and network stay open by design: this stops file/OS *destruction*, not
exfiltration (the chosen boundary). Fail-closed: when no mechanism is available
the caller (``bash.py``) refuses to run, unless the human explicitly opts out.

The Seatbelt profile here was validated empirically (writes confined; store/cache/
``*.db``/``.env`` denied; reads, pipes, ``/dev/null``, git, and python all work).
``sandbox-exec`` is Apple-deprecated but shipped and functional (Chromium, Claude
Code use it). The ``bwrap`` path is best-effort and unverified on the macOS dev box.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

from .policy import (
    PolicyViolation,
    _PROTECTED_DIRS,
    _PROTECTED_NAMES,
    _PROTECTED_SUFFIXES,
)

_SANDBOX_EXEC = "/usr/bin/sandbox-exec"


def mechanism() -> str | None:
    """The OS sandbox available here: ``'seatbelt'`` (macOS), ``'bwrap'`` (Linux), or None."""
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if shutil.which("bwrap"):
        return "bwrap"
    return None


def seatbelt_profile(root: Path) -> str:
    """Build the Seatbelt profile confining writes to ``root`` (realpath-resolved).

    Allow-by-default (reads/exec/network), then deny ALL writes, then re-allow the
    workspace + system temp + the standard ``/dev`` fds, then re-deny the protected
    paths. Seatbelt is last-match-wins, so the final deny block beats the workspace
    allow for ``store/``, ``cache/``, ``*.db``, ``*.key``, and the secret names.
    """
    r = str(root.resolve())  # Seatbelt matches realpaths (macOS /tmp -> /private/tmp)
    # The system temp dir resolved: on macOS $TMPDIR is /private/var/folders/.../T,
    # which is NOT under /private/tmp — without allowing it, `mktemp` and any tool
    # that respects $TMPDIR fail with a confusing "Operation not permitted".
    systmp = str(Path(tempfile.gettempdir()).resolve())
    # ponytail: paths are embedded as quoted Seatbelt strings; a workspace path
    # containing a literal `"` would break the profile — not a real case here.
    denies = [f'    (subpath "{r}/{d}")' for d in sorted(_PROTECTED_DIRS)]
    denies += [f'    (regex #"{re.escape(s)}$")' for s in _PROTECTED_SUFFIXES]  # \.db$  \.key$
    denies += [f'    (regex #"/{re.escape(n)}$")' for n in sorted(_PROTECTED_NAMES)]
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny file-write*)\n"
        "(allow file-write*\n"
        f'    (subpath "{r}")\n'
        f'    (subpath "{systmp}")\n'
        # intentional shared-scratch allowance (world temp); the *.db/*.key/.env
        # denies below still apply here, so no protected material can land in temp.
        '    (subpath "/private/tmp")\n'
        '    (subpath "/private/var/tmp")\n'
        '    (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr")\n'
        '    (subpath "/dev/fd") (regex #"^/dev/tty"))\n'
        "(deny file-write*\n" + "\n".join(denies) + ")"
    )


def wrap(command: str, root: Path) -> list[str]:
    """argv that runs ``command`` under the active sandbox, writes confined to ``root``.

    Raises ``PolicyViolation`` if no mechanism is available (caller decides whether
    that is fatal — see ``bash.py``'s fail-closed gate).
    """
    mech = mechanism()
    if mech == "seatbelt":
        return [_SANDBOX_EXEC, "-p", seatbelt_profile(root), "/bin/bash", "-c", command]
    if mech == "bwrap":
        r = str(root.resolve())
        # ponytail: unverified on the macOS dev box — confine to the workspace by
        # ro-binding everything and rw-binding only root + /tmp, then ro-bind the
        # protected dirs back. The *.db/*.env suffix denies are Seatbelt-only (bwrap
        # binds are path-, not pattern-based); verify on Linux before relying on it.
        argv = ["bwrap", "--die-with-parent", "--ro-bind", "/", "/",
                "--dev", "/dev", "--proc", "/proc",
                "--bind", r, r, "--bind", "/tmp", "/tmp"]
        for d in sorted(_PROTECTED_DIRS):
            p = f"{r}/{d}"
            if Path(p).exists():
                argv += ["--ro-bind", p, p]
        return argv + ["/bin/bash", "-c", command]
    raise PolicyViolation("no OS sandbox mechanism available")
