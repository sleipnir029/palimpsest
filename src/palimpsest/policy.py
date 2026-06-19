"""Constrained-autonomy policy — the code-level boundary for agent writes/exec.

palimpsest runs like Claude Code: spawned in a workspace, it may freely read,
edit, create, and run content *in that workspace*. The STRUCTURED write tools —
``write_file``/``edit_file`` — route through ``assert_writable`` here, so the
agent cannot reason its way around the workspace boundary: it is enforced in
code, not suggested in a prompt. That is the thesis's central claim made
concrete. ``bash`` is the deliberate exception — a supervised escape hatch
(cwd-pinned but NOT filesystem-fenced; see bash.py) whose integrity relies on the
human + git, the same model Claude Code uses for shell access.

The workspace root is configurable via ``$PALIMPSEST_WORKSPACE``. In development
(engine + tests live in this repo) it defaults to a gitignored ``./workspace``
sandbox, so the write/edit tools have a real playground that cannot touch the
engine (``src/palimpsest/``) or the test fixtures (this repo's ``store/``,
``cache/``, ``papers/``) — they are simply *outside the workspace*. (bash can
reach those via an absolute path; it is trusted-but-supervised, not fenced.) In
deployment the root is the spawned folder and the same logic applies unchanged;
there the graph store / parser cache / ledger live *inside* the workspace, and
the protected-path rules below keep them off-limits to write_file/edit_file.
"""

from __future__ import annotations

import os
from pathlib import Path


class PolicyViolation(Exception):
    """Raised when a write/exec would breach the workspace or an invariant."""


def workspace_root() -> Path:
    """Absolute root for write_file/edit_file confinement and bash's default cwd.

    (write_file/edit_file are *confined* here; bash only *defaults* its cwd here —
    bash is not fenced. See the module docstring.)
    """
    return Path(os.environ.get("PALIMPSEST_WORKSPACE", "workspace")).resolve()


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# Correctness-critical paths that stay pipeline-only EVEN inside the workspace:
# the RDF graph store and parser cache (provenance) and the cost ledger (budget),
# plus the read-only secrets config. Matched workspace-relative.
#
# NOTE these protect the *structured* write tools (write_file/edit_file) only, and
# match by top-level dir name / filename convention. They are NOT a defence against
# `bash` (which can write any path — see bash.py) and a ledger renamed off `.db`
# would slip through; a deployment that relocates these should derive the protected
# paths from config rather than these literals.
_PROTECTED_DIRS = {"store", "cache"}
_PROTECTED_NAMES = {"config.txt", ".env"}  # secrets — set via config.set_value, not write_file


def is_secret_path(path: str) -> bool:
    """True if reading this path surfaces secret content that must not be persisted.

    Used by the session transcript (T66) to redact a ``read_file`` of a secret
    before it is logged. Matches by basename/suffix against the same secret set
    ``assert_writable`` protects (``_PROTECTED_NAMES`` + ``*.key``); ``*.db`` is
    excluded — it is gitignored and ``read_file`` refuses binary, so it never
    leaks. Not ``resolve()``d: only the name/suffix matters and we avoid touching
    the filesystem. Known limit (accepted for this human-supervised threat model):
    basename matching catches ``.env``, ``/abs/.env`` and ``../.env``, but a symlink
    with a non-secret name (``link`` -> ``.env``) would evade it — closing that would
    require a filesystem ``realpath`` we deliberately avoid here. Defence-in-depth: the
    transcript is gitignored, so even an un-redacted secret never reaches a commit.
    """
    if not path:
        return False
    p = Path(path)
    return p.name in _PROTECTED_NAMES or p.suffix == ".key"


def assert_writable(path: str) -> Path:
    """Return the resolved path if the agent may write it, else raise.

    Allows any path inside the workspace root EXCEPT the pipeline-managed graph
    store / parser cache, the cost-ledger db (``*.db``), and the secrets config.
    ``resolve()`` canonicalises ``..`` and symlinks, so neither can escape.
    """
    root = workspace_root()
    p = Path(path).resolve()
    if not _within(p, root):
        raise PolicyViolation(
            f"outside workspace: {path!r} is not under {root} — the engine and "
            "test fixtures are off-limits; write inside the workspace"
        )
    rel = p.relative_to(root)
    if rel.parts and rel.parts[0] in _PROTECTED_DIRS:
        raise PolicyViolation(
            f"protected: {rel.parts[0]}/ is written only via the pipeline "
            "(provenance/cache), never by direct file edits"
        )
    if p.name in _PROTECTED_NAMES or p.suffix in (".db", ".key"):
        raise PolicyViolation(
            f"protected: {p.name} — secrets/ledger are not agent-writable"
        )
    return p


# Bash foot-gun guard — NOT a security boundary. It catches the obvious
# un-metered-spend invocations (the pipeline CLI, RunPod CLIs), but a shell can
# always reach paid endpoints another way (e.g. `python -c "import
# palimpsest.pipeline; ..."`), so it cannot be exhaustive. The €-budget is
# enforced *in-process* by the CostMeter gate on the agent/extract call path; any
# spend a bash subprocess starts is outside that gate and the human's responsibility.
_DENIED_BASH = ("python -m palimpsest", "runpodctl", "runpod ")


def assert_bash_allowed(command: str) -> None:
    """Raise on an obvious un-metered-spend command (best-effort foot-gun guard)."""
    low = " ".join(command.strip().lower().split())  # collapse whitespace evasions
    for bad in _DENIED_BASH:
        if bad in low:
            raise PolicyViolation(
                f"blocked: {bad!r} can incur un-metered spend — use the "
                "extract_paper tool (metered) for pipeline runs"
            )
