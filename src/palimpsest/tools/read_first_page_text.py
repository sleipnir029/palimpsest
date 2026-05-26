"""read_first_page_text tool (T08): return the text of a PDF's first page.

The card's escape hatch for the T08 smoke: read_paper surfaces no text, so the
model can't answer "what is the title?" from metadata alone. This extracts the
first page's text via fitz so the title (and authors, abstract) are visible.
Cheap, local, lookup-only — NOT a parser in the T16 comparison.
"""

from __future__ import annotations

import fitz  # pymupdf imports as `fitz` for legacy reasons

from . import register


@register("read_first_page_text", {
    "description": "Return the plain text of the first page of a PDF (e.g. to read its title).",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
})
def read_first_page_text(path: str) -> str:
    return fitz.open(path)[0].get_text()
