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
    # template wired the right stream URL + sha into the viewer
    assert f"/paper/{sha}/pdf" in page.text
    assert sha[:12] in page.text
