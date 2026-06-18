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

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dulwich import porcelain
from dulwich.diff_tree import tree_changes
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


# Commit message for an /undo revert. Used both to write the revert commit and to
# recognise it on read, so plain repeated /undo is idempotent (a no-op) rather than
# a redo — without it, a revert would look like fresh untagged work on top of HEAD.
_UNDO_MSG_PREFIX = "undo: restore workspace to "


@dataclass
class UndoResult:
    """Outcome of ``undo_last_turn`` — what the TUI reports back to the human."""

    undone: bool
    detail: str
    target_tag: str | None = None
    revert_sha: str | None = None
    changed: list[str] = field(default_factory=list)


def _turn_tags_from_head(repo: Repo) -> list[tuple[bytes, str]]:
    """``(commit_sha, tag_name)`` for ``turn-*`` tags reachable from HEAD, newest-first.

    Ordered by HEAD's ancestry (not tag name) so it stays correct across sessions,
    where the ``turn-<session>-<n>`` numbering restarts each process.
    """
    tag_by_commit: dict[bytes, str] = {}
    for ref, sha in repo.get_refs().items():
        if ref.startswith(b"refs/tags/turn-"):
            tag_by_commit.setdefault(sha, ref[len(b"refs/tags/"):].decode())
    return [
        (e.commit.id, tag_by_commit[e.commit.id])
        for e in repo.get_walker()
        if e.commit.id in tag_by_commit
    ]


def _undo_target(repo: Repo, turns: list[tuple[bytes, str]]) -> tuple[bytes, str] | None:
    """Pick the commit to restore to for a single-step undo, newest-first ``turns``.

    Normally the previous turn tag (``turns[1]``). But a turn that committed work
    yet never tagged a boundary — one that errored out (``MaxTurnsExceeded`` skips
    ``tag_turn``) — leaves untagged commits above the newest tag; those should be
    discarded back to that tag (``turns[0]``). Our own ``/undo`` reverts are also
    untagged but must be ignored here, else repeated ``/undo`` would *redo*.
    """
    last_end_sha, last_tag = turns[0]
    for e in repo.get_walker():  # HEAD-first, down to the newest turn tag
        if e.commit.id == last_end_sha:
            break
        msg = e.commit.message.decode("utf-8", "replace")
        if not msg.startswith(_UNDO_MSG_PREFIX):  # genuine incomplete-turn work
            return turns[0]
    return turns[1] if len(turns) >= 2 else None


def undo_last_turn() -> UndoResult:
    """Restore the workspace to the previous turn's state, recorded as a new commit.

    Single-step undo (T64): restores the working tree + index to the previous turn
    boundary, then commits that restoration ON TOP of HEAD. HEAD never moves
    backwards, so history stays append-only and every prior turn is still reachable
    (``git log`` / any viewer shows the full trail). Best-effort: a no-op (not an
    error) when there is nothing to undo.

    Notes / known limits:
    - Uncommitted tracked changes in the working tree are discarded by the restore
      (the agent checkpoints per action, so this window is normally empty).
    - Chaining undo with *new* work between (``/undo`` → a turn → ``/undo``) restores
      to the previous turn tag, not a true undo stack — multi-step undo is deferred.
    """
    root = workspace_root()
    if not (root / ".git").exists():
        return UndoResult(False, "no workspace repo — nothing to undo")
    repo = Repo(str(root))
    try:
        head = repo.head()
    except KeyError:
        return UndoResult(False, "no commits yet — nothing to undo")

    turns = _turn_tags_from_head(repo)
    if not turns:
        return UndoResult(False, "no turn tags — nothing to undo")
    target = _undo_target(repo, turns)
    if target is None:
        # Only the first turn exists and nothing incomplete sits above it: there is
        # no prior turn-state to restore. Refuse rather than emptying the workspace.
        return UndoResult(False, "this is the first turn — no prior turn to undo")

    target_sha, target_tag = target
    head_tree = repo[head].tree
    target_tree = repo[repo[target_sha].tree]  # Tree object (see reset note below)
    changes = list(tree_changes(repo.object_store, head_tree, target_tree.id))
    # An add/delete leaves one side None; take whichever entry carries the path.
    changed = sorted((c.new or c.old).path.decode() for c in changes)
    if not changed:
        return UndoResult(True, f"already at {target_tag} — nothing to undo", target_tag)

    # Restore the index + working tree to the target tree, removing files the undone
    # turn added too. Passing a *Tree* (not a commit-ish) makes porcelain.reset leave
    # HEAD in place — so we do NOT rewrite history. Guard that invariant loudly: if a
    # future dulwich changes this, fail rather than silently rewinding the branch.
    porcelain.reset(repo, "hard", target_tree)
    if repo.head() != head:
        raise RuntimeError("undo: porcelain.reset moved HEAD — append-only invariant broken")
    # Record the restoration as a new commit (parent = HEAD ⇒ append-only).
    sha = porcelain.commit(
        repo,
        message=f"{_UNDO_MSG_PREFIX}{target_tag}".encode("utf-8"),
        author=_AUTHOR,
        committer=_AUTHOR,
    )
    revert_sha = sha.decode() if isinstance(sha, bytes) else sha
    return UndoResult(True, f"undid last turn → {target_tag}", target_tag, revert_sha, changed)
