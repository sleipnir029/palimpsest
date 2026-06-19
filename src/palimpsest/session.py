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
from pathlib import Path

from .policy import workspace_root


class SessionLog:
    """Append-only JSONL transcript of the agent's messages in the workspace."""

    def __init__(self, path: Path | None = None) -> None:
        # An explicit override (tests) or None → the default workspace path, resolved
        # lazily in _path() so env changes after construction are honored.
        self._override = path

    def _path(self) -> Path:
        return self._override or workspace_root() / ".palimpsest" / "session.jsonl"

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
        """Read the transcript back into message dicts (``[]`` if absent).

        ``limit`` keeps only the last N records (tail), for a future bounded resume.
        """
        path = self._path()
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Tolerate a truncated tail: append is not atomic, so a process
                # killed mid-write leaves a partial last line — exactly the
                # crash-then-resume case load() must survive. Skip it, don't raise.
                continue
        return records[-limit:] if limit is not None else records
