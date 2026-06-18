"""`write_file` tool — create or overwrite a file in the workspace.

Routes through ``policy.assert_writable``: the write lands only if it's inside
the workspace and not a pipeline-managed/secret path. Parent directories are
created so the agent can build new structure (e.g. ``analysis/notes.md``).
"""

from __future__ import annotations

from palimpsest.policy import assert_writable

from . import register


@register("write_file", {
    "description": "Create or overwrite a text file in the workspace (parent dirs are created). Refused outside the workspace or for protected paths.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
})
def write_file(path: str, content: str) -> str:
    p = assert_writable(path)  # raises PolicyViolation → surfaced to the agent
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {path}"
