"""`edit_file` tool — exact-match single replacement in a workspace file.

Like the Claude Code edit primitive: ``old_string`` must occur exactly once, so
edits are unambiguous and the agent must supply enough context to disambiguate.
Routes through ``policy.assert_writable`` (same boundary as write_file).
"""

from __future__ import annotations

from palimpsest.policy import assert_writable

from . import register


@register("edit_file", {
    "description": (
        "Replace an exact, unique substring in a workspace file with new text. "
        "old_string must match once; include surrounding context if it isn't unique."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
        },
        "required": ["path", "old_string", "new_string"],
    },
})
def edit_file(path: str, old_string: str, new_string: str) -> str:
    p = assert_writable(path)  # boundary check before we read/write
    text = p.read_text(encoding="utf-8")
    n = text.count(old_string)
    if n == 0:
        return f"error: old_string not found in {path}"
    if n > 1:
        return f"error: old_string occurs {n} times in {path}; add context to make it unique"
    p.write_text(text.replace(old_string, new_string), encoding="utf-8")
    return f"edited {path}"
