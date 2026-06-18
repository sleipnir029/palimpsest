"""`read_file` tool — read any text file in the workspace.

Perception for the agent: source, parser output, ground-truth markdown, configs.
Reads are unconditionally safe (the constrained-autonomy policy gates *writes*,
not reads), but the content is capped: a raw parser dump (docling ~19 MB) would
blow the context window and the budget if returned whole. Oversized reads come
back truncated with an explicit marker so the agent knows to narrow its request.
Binary files (e.g. a PDF passed by mistake) are refused rather than decoded to
replacement-character garbage — read_paper is the tool for PDFs.
"""

from __future__ import annotations

from pathlib import Path

from . import register

_MAX_CHARS = 100_000  # ~25-30K tokens; enough for source/GT, caps giant parser JSON


@register("read_file", {
    "description": (
        "Read a text file from the workspace and return its contents. Large files "
        "are truncated to the first ~100K characters with a marker; narrow your "
        "request if you hit it. For PDFs use read_paper, not this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
})
def read_file(path: str) -> str:
    data = Path(path).read_text(encoding="utf-8", errors="replace")
    # A NUL in the head is the reliable tell for binary content (PDF, images);
    # decoding it to replacement chars would waste context, so refuse cleanly.
    if "\x00" in data[:1024]:
        return f"binary file: {path} — use read_paper for PDFs"
    if len(data) > _MAX_CHARS:
        return data[:_MAX_CHARS] + f"\n\n[truncated: file is {len(data)} chars, showing first {_MAX_CHARS}]"
    return data
