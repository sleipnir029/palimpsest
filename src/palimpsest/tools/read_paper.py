"""read_paper tool (T07): load a PDF and report its identity and size.

Returns the SHA-256 of the raw bytes (the parse-once cache key, T15), the page
count, and the byte length. No parsing or caching happens here — this is the
cheap front door that downstream parser dispatch (T16) keys off of.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import fitz  # pymupdf imports as `fitz` for legacy reasons

from . import register


@register("read_paper", {
    "description": "Load a PDF and return its SHA-256, page count, and size.",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
})
def read_paper(path: str) -> dict:
    data = Path(path).read_bytes()
    # Open from the same bytes we hashed, so sha256 and page_count can never
    # describe different content (the sha256 becomes the T15 cache key).
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "page_count": fitz.open(stream=data, filetype="pdf").page_count,
        "bytes_len": len(data),
        "path": path,
    }
