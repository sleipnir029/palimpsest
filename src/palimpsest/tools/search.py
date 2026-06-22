"""`search` tool — regex search over workspace text files (read-only, €0).

A first-class, structured alternative to ``bash grep``: the agent gets
``file:line: text`` hits without spawning a shell. Reads only (policy fences
*writes*, not reads), but still kept inside the workspace so it never wanders the
engine tree. Stdlib only — no ripgrep dependency.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from palimpsest.policy import is_secret_path, workspace_root

from . import register

_MAX_HITS = 100
_SKIP_DIRS = {".git", ".palimpsest", "__pycache__", "node_modules", ".venv"}
_TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".csv", ".tsv",
    ".rdf", ".ttl", ".nt", ".sparql", ".rq", ".cfg", ".ini", ".js", ".ts",
    ".html", ".css", ".sh", ".rst", "",  # "" = extensionless (README, etc.)
}


@register("search", {
    "description": (
        "Search workspace text files for a regex pattern (read-only, €0). Returns "
        "matching 'relpath:line: text' hits, capped. Optional path narrows to a subdir."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "a Python regular expression"},
            "path": {"type": "string", "description": "subdir under the workspace (default: whole workspace)"},
        },
        "required": ["pattern"],
    },
})
def search(pattern: str, path: str = ".") -> str:
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"error: bad regex: {exc}"
    root = workspace_root()
    base = (root / path).resolve()
    if root != base and root not in base.parents:
        return f"error: {path!r} is outside the workspace"
    if not base.exists():
        return f"error: no such path: {path}"

    hits: list[str] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]  # prune in place
        for fn in filenames:
            fp = Path(dirpath) / fn
            if fp.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            if is_secret_path(str(fp)):  # never surface .env/config.txt/*.key content
                continue
            try:
                lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if rx.search(line):
                    hits.append(f"{fp.relative_to(root)}:{i}: {line.strip()[:200]}")
                    if len(hits) >= _MAX_HITS:
                        return "\n".join(hits) + f"\n… (capped at {_MAX_HITS} hits)"
    return "\n".join(hits) if hits else "(no matches)"
