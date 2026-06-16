"""T31 — bbox-highlight wiring checks for the provenance viewer.

The card sketched "httpx-fetch the page, parse for data-bbox, assert a row
exists". Under T30 the rows are NOT server-rendered: `/data` returns JSON and the
template builds rows client-side via fetch(). So with httpx (no JS engine) the
honest checks are:

  1. /static/pdf-overlay.js is served and defines the two globals the rows call.
  2. The served viewer page carries the row-building wiring (dataset.bbox /
     dataset.parser / highlightBox + the overlay script tag). Rows are built in
     JS, so the source carries the `dataset.*` assignments, not literal
     `data-*` attributes.
  3. When store/ holds data for a paper, /data yields at least one triple with a
     4-tuple bbox — the "at least one row exists" intent, at the data layer.

Live DOM verification (real hover -> drawn overlay) is the manual step in the
card; it needs a browser and a docling-backed store/, out of scope for the suite.

The card suggested @pytest.mark.slow, but conftest.py defines `slow` as "hits the
network or paid APIs" — these in-process TestClient checks do neither (the card
assumed a Playwright path; this httpx adaptation is fast + offline), so the marker
is omitted to keep its meaning honest.
"""

import pytest
from fastapi.testclient import TestClient

from palimpsest.viewer.app import _pdf_index, app

client = TestClient(app)


def test_overlay_js_served_and_defines_globals():
    r = client.get("/static/pdf-overlay.js")
    assert r.status_code == 200
    assert "function highlightBox" in r.text
    assert "function clearHighlights" in r.text


def test_viewer_page_wires_hover_highlight():
    index = _pdf_index()
    if not index:
        pytest.skip("no PDFs in papers/")
    sha = next(iter(index))

    page = client.get(f"/paper/{sha}").text
    assert "/static/pdf-overlay.js" in page  # overlay globals loaded
    assert "highlightBox(" in page  # rows call it on hover
    # rows are built in JS, so the source carries the dataset.* assignments
    for token in ("dataset.bbox", "dataset.page", "dataset.parser"):
        assert token in page  # provenance carried onto each row


def test_data_endpoint_has_a_bbox_row():
    index = _pdf_index()
    if not index:
        pytest.skip("no PDFs in papers/")
    sha = next(iter(index))

    triples = client.get(f"/paper/{sha}/data").json()["triples"]
    if not triples:
        pytest.skip(f"store/ has no extracted data for {sha[:12]}")
    with_bbox = [t for t in triples if isinstance(t.get("bbox"), list) and len(t["bbox"]) == 4]
    assert with_bbox, "expected at least one triple carrying a 4-tuple bbox"
