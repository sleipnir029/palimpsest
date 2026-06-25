"""Tighten a value's source box to the exact text via the PDF text layer (fitz).

`extract()` pins a measurement's Evidence to the parser span that states the
value — but a span is a whole text block, so the stored box is the paragraph.
On born-digital PDFs we can do better: `fitz.search_for` locates the exact value
text and returns a tight rect. We store it in PDF points, bottom-left origin
(docling's convention), so the viewer's existing points transform renders it for
every parser — no per-parser reference size needed.

When the text can't be located unambiguously (LaTeX/OCR mismatch, a value that
repeats with no disambiguating context, or a scanned page with no text layer),
the caller's parser-native fallback box is returned unchanged. We never fabricate
a box: a refined box always corresponds to text actually found on the page.
"""

from __future__ import annotations

import re
import unicodedata

Bbox = tuple[float, float, float, float]

# LaTeX wrappers/commands the PDF text layer never contains: \mathrm, \,, $, ^_{}.
_LATEX = re.compile(r"\\[a-zA-Z]+|\\,|[${}^_]")


def _clean(text: str) -> str:
    """Strip LaTeX, NFKC-fold (− → -, µ → μ), and collapse whitespace so the
    source_text can match the PDF text layer."""
    text = unicodedata.normalize("NFKC", text)
    return " ".join(_LATEX.sub(" ", text).split())


def _to_bottom_left(rect, page_height: float) -> Bbox:
    """fitz Rect (top-left points) → PDF user space (bottom-left), docling's convention."""
    return (rect.x0, page_height - rect.y1, rect.x1, page_height - rect.y0)


def _value_str(value) -> str:
    """The value's printed digits as a search string, or '' if not numeric."""
    try:
        return "%g" % float(value)
    except (TypeError, ValueError):
        return ""


def _phrase(clean_src: str, digits: str, window: int = 3) -> str | None:
    """~`window` words on each side of the token containing `digits` — specific
    enough to disambiguate a value that repeats on the page."""
    words = clean_src.split()
    for i, w in enumerate(words):
        if digits and digits in re.sub(r"\D", "", w):
            return " ".join(words[max(0, i - window):i + window + 1])
    return None


def tighten_bbox(page, value, source_text: str, fallback: Bbox) -> tuple[Bbox, bool]:
    """Return ``(tight_bbox_bottom_left_points, refined)`` for ``value`` on ``page``.

    Tries a phrase from ``source_text`` first (disambiguates repeats), then the bare
    value (only if it occurs exactly once). No confident, unique hit → returns
    ``(fallback, False)`` so the parser-native box is kept rather than guessed.
    """
    vs = _value_str(value)
    if not vs:
        return fallback, False
    digits = re.sub(r"\D", "", vs)
    H = page.rect.height
    for query in (_phrase(_clean(source_text), digits), vs):
        if not query:
            continue
        rects = page.search_for(query)
        if len(rects) == 1:  # unique → safe to pin
            return _to_bottom_left(rects[0], H), True
    return fallback, False


if __name__ == "__main__":  # ponytail: one runnable check, no framework
    import sys
    from pathlib import Path

    import fitz

    pdf = Path("papers/s41467-022-35426-8.pdf")
    if not pdf.exists():
        sys.exit(f"fixture missing: {pdf}")
    pg = fitz.open(pdf)[0]
    big = (1.0, 2.0, 590.0, 780.0)
    box, refined = tighten_bbox(pg, 13, "Received: 13 July 2022", big)
    assert refined and (box[2] - box[0]) < 200 and box[1] < box[3], box
    assert tighten_bbox(pg, 2022, "2022", big) == (big, False)  # ambiguous → fallback
    print("ok:", box)
