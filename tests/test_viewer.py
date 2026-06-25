"""Offline smoke tests for the T29 FastAPI viewer skeleton.

Routing + content-type only — no graph/data assertions (the data pane is T30).
The happy-path PDF stream couples to whatever is in `papers/`; it self-skips if
that directory is empty so the suite stays runnable on a bare checkout.
"""

import pytest
from fastapi.testclient import TestClient

from palimpsest.viewer.app import _pdf_index, app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_home_renders():
    r = client.get("/")
    assert r.status_code == 200
    assert "palimpsest" in r.text.lower()


def test_unknown_paper_404():
    assert client.get("/paper/deadbeef").status_code == 404


def test_unknown_pdf_404():
    assert client.get("/paper/deadbeef/pdf").status_code == 404


def test_vendored_pdfjs_is_served():
    # A renamed/missing vendor file is the silent failure mode for this card.
    assert client.get("/static/pdfjs/pdf.min.mjs").status_code == 200
    assert client.get("/static/pdfjs/pdf.worker.min.mjs").status_code == 200
    # cmaps + standard fonts so CID/CJK and non-embedded-font PDFs render
    assert client.get("/static/pdfjs/cmaps/78-EUC-H.bcmap").status_code == 200
    assert client.get("/static/pdfjs/standard_fonts/FoxitDingbats.pfb").status_code == 200


def test_malformed_pdf_does_not_break_home(tmp_path, monkeypatch):
    from palimpsest.viewer import app as viewer_app

    (tmp_path / "junk.pdf").write_bytes(b"not a real pdf")
    monkeypatch.setattr(viewer_app, "PAPERS_DIR", tmp_path)
    viewer_app._pdf_index.cache_clear()
    try:
        assert viewer_app._pdf_index() == {}  # unreadable file skipped, not raised
        assert client.get("/").status_code == 200
    finally:
        viewer_app._pdf_index.cache_clear()  # don't leak the tmp index to other tests


def test_known_pdf_streams_and_renders():
    index = _pdf_index()
    if not index:
        pytest.skip("no PDFs in papers/")
    sha = next(iter(index))

    r = client.get(f"/paper/{sha}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"

    page = client.get(f"/paper/{sha}")
    assert page.status_code == 200
    # template wires the full sha into the viewer JS, which builds /paper/${sha}/pdf
    # client-side (the redesign moved URL construction from Jinja to JS).
    assert f'const sha = "{sha}"' in page.text
    assert sha[:12] in page.text


def test_collect_triples_tolerates_bad_literals():
    """A single malformed page/bbox literal must degrade to None, not 500 the route
    (so the data pane renders the value with no box, instead of failing the cell)."""
    from palimpsest.viewer.app import _bbox, _int

    assert _int("3") == 3 and _int(None) is None and _int("3.5") is None and _int("x") is None
    good = {"bx0": "1.0", "by0": "2.0", "bx1": "3.0", "by1": "4.0"}
    assert _bbox(good) == [1.0, 2.0, 3.0, 4.0]
    assert _bbox({**good, "bx1": "oops"}) is None  # one bad coord → whole box dropped
    assert _bbox({**good, "by1": None}) is None
