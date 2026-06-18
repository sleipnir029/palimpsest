"""Workspace versioning (dulwich) — git-log everything the agent does.

The agent is spawned in a workspace; every mutating action is committed to a git
repo *inside that workspace*, so the human can see the tree in any git viewer and
undo anything (``git revert``). This is the safety net that makes bash's unfenced
escape hatch acceptable: in-workspace changes are fully reversible and auditable.

Two granularities (Rahat's choice): a commit per write action (``checkpoint``,
fine-grained undo) and a lightweight tag per agent turn (``tag_turn``, a readable
turn-level view). Secrets and bulk/provenance state are never committed —
``ensure_repo`` writes a ``.gitignore`` covering config.txt, the ledger (*.db),
and the graph store / parser cache.

Best-effort by design: ``checkpoint``/``tag_turn`` no-op when the workspace isn't
a git repo (so tests and non-workspace runs are untouched). The agent call sites
also swallow failures so a versioning hiccup never breaks a turn; tests call these
directly and DO see real errors.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

from .policy import workspace_root

_AUTHOR = b"palimpsest-agent <agent@palimpsest.local>"
_SESSION = datetime.now().strftime("%Y%m%d-%H%M%S")  # per-process tag namespace
_turn = 0
_last_tagged: bytes | None = None

_GITIGNORE = (
    "# palimpsest workspace — secrets + bulk/provenance state are never committed\n"
    ".env\n"
    "config.txt\n"
    "*.key\n"
    "*.db\n"
    "store/\n"
    "cache/\n"
    "__pycache__/\n"
    ".DS_Store\n"
)


def ensure_repo(root: Path | None = None) -> None:
    """Init the workspace git repo (+ .gitignore) if absent. Idempotent."""
    root = workspace_root() if root is None else root
    root.mkdir(parents=True, exist_ok=True)
    gi = root / ".gitignore"
    existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
    if not existing:
        gi.write_text(_GITIGNORE, encoding="utf-8")
    elif ".env" not in existing.splitlines():
        # An older workspace's .gitignore predates the secret-exclusion lines;
        # append them so .env / *.key can never be auto-committed (no leak).
        gi.write_text(existing.rstrip("\n") + "\n.env\n*.key\n", encoding="utf-8")
    if not (root / ".git").exists():
        porcelain.init(str(root))


def _has_changes(repo: Repo) -> bool:
    st = porcelain.status(repo)  # ignored excluded by default
    return bool(st.untracked) or bool(st.unstaged) or any(st.staged.values())


def checkpoint(message: str) -> str | None:
    """Commit all workspace changes (respecting .gitignore); None if nothing changed.

    Per-action granularity: called after each tool runs — a no-op for read-only
    tools (nothing staged) and a commit for mutating ones (incl. bash edits).
    ``porcelain.add`` with no paths stages adds, modifications, AND deletions.
    """
    root = workspace_root()
    if not (root / ".git").exists():
        return None
    repo = Repo(str(root))
    if not _has_changes(repo):
        return None
    porcelain.add(repo)  # git add -A, respecting .gitignore
    sha = porcelain.commit(
        repo, message=message.encode("utf-8"), author=_AUTHOR, committer=_AUTHOR
    )
    return sha.decode() if isinstance(sha, bytes) else sha


def tag_turn() -> str | None:
    """Lightweight tag at HEAD marking a turn boundary; skip if HEAD hasn't moved."""
    global _turn, _last_tagged
    root = workspace_root()
    if not (root / ".git").exists():
        return None
    repo = Repo(str(root))
    try:
        head = repo.head()
    except KeyError:
        return None  # no commits yet this session
    if head == _last_tagged:
        return None  # turn produced no commits — nothing to mark
    _turn += 1
    name = f"turn-{_SESSION}-{_turn}"
    repo.refs[f"refs/tags/{name}".encode("utf-8")] = head
    _last_tagged = head
    return name
