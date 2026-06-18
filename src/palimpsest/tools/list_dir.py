"""`list_dir` tool — list the entries of a directory.

Lets the agent discover the workspace (which papers exist, which parser outputs
are cached, what's in experiments/) before reading or acting. Directories are
suffixed with ``/`` so the agent can tell them from files in one glance.
"""

from __future__ import annotations

from pathlib import Path

from . import register


@register("list_dir", {
    "description": "List the files and subdirectories of a directory (one per line; directories end with '/').",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
})
def list_dir(path: str) -> str:
    p = Path(path)
    if not p.is_dir():
        return f"not a directory: {path}"
    entries = sorted(
        f"{e.name}/" if e.is_dir() else e.name for e in p.iterdir()
    )
    return "\n".join(entries) or "(empty)"
