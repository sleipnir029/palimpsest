"""Session transcript (T66) — a git-tracked append log of the agent's turns.

``Agent.messages`` lives only in memory, so a spawn forgets everything the moment
the process exits. ``SessionLog`` mirrors each message the agent appends to its
history into ``<workspace>/.palimpsest/session.jsonl`` (one JSON object per line),
so the run leaves a durable, human-readable record — the thesis's reflection trail
"for free" — and a future session can reload context via ``load()``.

Best-effort, gated like ``versioning.py``: it only writes when the workspace is an
initialized git repo (``workspace_root()/.git`` exists). Both spawn entrypoints call
``versioning.ensure_repo`` first, so in real runs the gate is always open. Unit tests
that build an ``Agent`` directly have no repo, so they write nothing — no pollution.
The path is resolved lazily on every call (never cached), so a ``$PALIMPSEST_WORKSPACE``
set after construction is honored — the same discipline ``versioning`` uses.

The transcript is deliberately **gitignored** (``.palimpsest/`` in the workspace
``.gitignore``): it is an append-only on-disk record, so ``/undo`` — which hard-resets
the tracked tree — can never truncate it, and a logged ``read_file`` result can never
reach a commit. Two consequences worth knowing: (1) ``Agent`` redacts secret-path
``read_file`` results before logging (see ``Agent._redact_secrets``); ``bash`` output
is NOT redacted (the supervised escape hatch, per policy.py). (2) A single writer per
workspace is assumed — concurrent agents could interleave lines; ``load`` tolerates a
torn tail but there is no file lock.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from .policy import workspace_root


def _sessions_dir() -> Path:
    return workspace_root() / ".palimpsest"


def session_paths() -> list[Path]:
    """Every session transcript file in the workspace, newest first (by mtime).

    Matches both rotated ``session-<id>.jsonl`` files and a legacy ``session.jsonl``.
    """
    d = _sessions_dir()
    if not d.exists():
        return []
    return sorted(d.glob("session*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def load_session(path: Path, limit: int | None = None) -> list[dict]:
    """Read one session file into message dicts (``[]`` if absent), tolerant of a
    torn last line (a process killed mid-append)."""
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # skip a truncated tail rather than raise
    return records[-limit:] if limit is not None else records


def prior_sessions(exclude: Path | None = None) -> list[Path]:
    """Session files excluding the current launch's, newest first — the resume picker."""
    return [p for p in session_paths() if exclude is None or p != exclude]


def session_recap(path: Path) -> str:
    """The session's first user prompt, for a one-line picker label."""
    for rec in load_session(path):
        if rec.get("role") == "user" and isinstance(rec.get("content"), str):
            return rec["content"].strip()[:60] or "(empty prompt)"
    return "(no prompts)"


def recent_inputs(max_sessions: int = 5, max_inputs: int = 200) -> list[str]:
    """User-typed lines from the most recent sessions, oldest→newest, adjacent-deduped —
    seeds the TUI's up-arrow history across launches (A5 / cross-session)."""
    inputs: list[str] = []
    for path in reversed(session_paths()[:max_sessions]):  # oldest session first
        for rec in load_session(path):
            if rec.get("role") == "user" and isinstance(rec.get("content"), str):
                line = rec["content"].strip()
                # Includes slash commands (the TUI suppresses the menu while browsing a
                # recalled line, so they no longer hijack up/down). Adjacent-deduped.
                if line and (not inputs or inputs[-1] != line):
                    inputs.append(line)
    return inputs[-max_inputs:]


class SessionLog:
    """Append-only JSONL transcript of one launch's agent messages (rotated per run)."""

    def __init__(self, path: Path | None = None, session_id: str | None = None) -> None:
        # An explicit override (tests) or None → a rotated per-launch file. The id is
        # fixed at construction (one file per run); the dir resolves lazily in _path()
        # so a $PALIMPSEST_WORKSPACE set after construction is still honored.
        self._override = path
        self._session_id = session_id or f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"

    def _path(self) -> Path:
        return self._override or _sessions_dir() / f"session-{self._session_id}.jsonl"

    @property
    def current_path(self) -> Path:
        """This launch's transcript file (the resume picker excludes it)."""
        return self._path()

    def _enabled(self) -> bool:
        """Only log inside an initialized workspace repo (mirrors versioning's gate)."""
        return (workspace_root() / ".git").exists()

    def append(self, message: dict) -> None:
        """Append one message dict as a JSON line; no-op when the gate is closed.

        Stores exactly the ``{"role", "content"}`` dict the agent appends to its
        history (with secret-path reads already redacted by the caller), so ``load()``
        round-trips straight back into ``Agent.messages``. ``default=str`` is a safety
        net for any non-JSON-native block. Single-writer: no lock (see module docs).
        """
        if not self._enabled():
            return
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(message, default=str) + "\n")

    def load(self, limit: int | None = None) -> list[dict]:
        """Reload a transcript into message dicts. This launch's own file if it has one
        yet, else the most recent session on disk — so a fresh ``SessionLog()`` (tests,
        and the resume fallback) still finds the last session. ``limit`` tails the last
        N records. Tolerant of a torn last line (see ``load_session``)."""
        own = self._path()
        if own.exists():
            return load_session(own, limit)
        paths = session_paths()
        return load_session(paths[0], limit) if paths else []
