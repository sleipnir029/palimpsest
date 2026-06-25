"""Tests for geometry.tighten_bbox — relocating a value's source box to the exact
text via the PDF text layer (fitz), in PDF points / bottom-left origin.

Integration tests use a real born-digital fixture (papers/s41467-022-35426-8.pdf);
page 0 anchors verified with fitz: page is 595.28x790.87 pt, "Received: 13 July
2022" occurs once, the bare token "2022" occurs four times (ambiguous).
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from palimpsest.tools.geometry import _clean, _to_bottom_left, tighten_bbox

_PDF = Path(__file__).resolve().parents[1] / "papers" / "s41467-022-35426-8.pdf"
_FALLBACK = (1.0, 2.0, 590.0, 780.0)  # a deliberately huge "whole block" box


@pytest.fixture
def page():
    if not _PDF.exists():
        pytest.skip(f"fixture PDF missing: {_PDF}")
    doc = fitz.open(_PDF)
    try:
        yield doc[0]
    finally:
        doc.close()


# ----- pure helpers ---------------------------------------------------------


def test_origin_conversion_top_left_to_bottom_left():
    """fitz top-left rect -> PDF user-space bottom-left (x0, H-y1, x1, H-y0)."""
    assert _to_bottom_left(fitz.Rect(10, 20, 50, 60), 100.0) == (10.0, 40.0, 50.0, 80.0)


def test_clean_strips_latex_for_text_layer_search():
    """LaTeX wrappers the PDF text layer never contains are removed; digits survive."""
    out = _clean("mass activity is 3343.37 \\, A g^{-1}_{Ir}")
    assert "3343.37" in out
    assert not any(c in out for c in "${}^\\")


# ----- tighten_bbox ---------------------------------------------------------


def test_tighten_finds_tight_box(page):
    """A locatable value yields a box far smaller than the block fallback, refined."""
    bbox, refined = tighten_bbox(page, 13, "Received: 13 July 2022", _FALLBACK)
    assert refined is True
    fw, fh = _FALLBACK[2] - _FALLBACK[0], _FALLBACK[3] - _FALLBACK[1]
    assert (bbox[2] - bbox[0]) < fw / 3 and (bbox[3] - bbox[1]) < fh / 3
    assert bbox[1] < bbox[3]  # bottom-left: y0 < y1


def test_tighten_disambiguates_repeated_value(page):
    """'2022' occurs 4x; the phrase from source_text pins the right occurrence."""
    bbox, refined = tighten_bbox(page, 2022, "Received: 13 July 2022", _FALLBACK)
    assert refined is True
    # 'Received: 13 July 2022' sits at the top of the page → small TL-y → large BL-y.
    received = page.search_for("Received: 13 July 2022")[0]
    expected = _to_bottom_left(received, page.rect.height)
    assert bbox[1] == pytest.approx(expected[1], abs=2.0)


def test_tighten_ambiguous_bare_value_falls_back(page):
    """No phrase context + a non-unique bare value → keep the native fallback box."""
    bbox, refined = tighten_bbox(page, 2022, "2022", _FALLBACK)
    assert refined is False
    assert bbox == _FALLBACK


def test_tighten_not_found_falls_back(page):
    """Value absent from the text layer → fallback, never fabricate a box."""
    bbox, refined = tighten_bbox(page, 999999, "phantom 999999 reading", _FALLBACK)
    assert refined is False
    assert bbox == _FALLBACK
