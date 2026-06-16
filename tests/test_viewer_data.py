"""T30 — /paper/{sha}/data JSON endpoint tests.

In production the data graph is read from a disk-backed RDFStore (RocksDB under
`store/`). Here we inject an in-memory store populated with one real
`Overpotential` via the same `insert_extraction` path the pipeline uses, so the
route is exercised offline with zero spend — mirroring how `test_viewer`
monkeypatches `PAPERS_DIR`/`_pdf_index`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from schema.generated.pydantic import Condition, Evidence, Overpotential, Paper

from palimpsest.store import RDFStore
from palimpsest.viewer import app as viewer_app

client = TestClient(viewer_app.app)

_SHA = "a" * 64  # hex-shaped sha256


def _store_with_one() -> RDFStore:
    store = RDFStore()
    store.insert_extraction(
        Overpotential(
            value=236.0,
            unit_label="mV",
            condition=Condition(current_density=10.0),
            evidence=Evidence(
                paper=Paper(sha256=_SHA, doi="10.1000/xyz", title="A paper"),
                page=3,
                bbox_x0=0.1, bbox_y0=0.2, bbox_x1=0.3, bbox_y1=0.4,
                parser_name="mineru",
                source_text="η = 236 mV at 10 mA/cm²",
            ),
        ),
        run_id="r1",
    )
    return store


def test_data_returns_triple_with_all_fields(monkeypatch):
    monkeypatch.setattr(viewer_app, "_graph_store", _store_with_one)
    r = client.get(f"/paper/{_SHA}/data")
    assert r.status_code == 200
    body = r.json()
    assert body["sha"] == _SHA
    assert len(body["triples"]) >= 1

    t = body["triples"][0]
    for field in (
        "id", "slot_path", "value", "unit",
        "page", "bbox", "parser_name", "source_text",
    ):
        assert field in t, f"missing {field}"

    assert t["id"].startswith("https://w3id.org/palimpsest/measurement/")
    assert t["slot_path"] == "Overpotential"  # friendly name, not the EMMO hash IRI
    assert t["value"] == 236.0
    assert t["unit"] == "mV"
    assert t["page"] == 3
    assert t["bbox"] == [0.1, 0.2, 0.3, 0.4]
    assert t["parser_name"] == "mineru"
    assert "236" in t["source_text"]


def test_data_measurement_without_value(monkeypatch):
    # value/unit/sourceText are OPTIONAL in the query (store skips None) — a
    # measurement missing them must still return one row with those as null and
    # the required page/bbox/parser_name intact.
    def _store() -> RDFStore:
        s = RDFStore()
        s.insert_extraction(
            Overpotential(
                evidence=Evidence(
                    paper=Paper(sha256=_SHA), page=1,
                    bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
                    parser_name="docling",
                ),
            ),
            run_id="r1",
        )
        return s

    monkeypatch.setattr(viewer_app, "_graph_store", _store)
    t = client.get(f"/paper/{_SHA}/data").json()["triples"][0]
    assert t["value"] is None and t["unit"] is None and t["source_text"] is None
    assert t["page"] == 1 and t["bbox"] == [0.0, 0.0, 1.0, 1.0]
    assert t["parser_name"] == "docling"


def test_data_filters_to_requested_paper(monkeypatch):
    # Two papers in one store: the palim:paper filter must return only the
    # requested paper's measurement.
    other = "c" * 64

    def _store() -> RDFStore:
        s = _store_with_one()  # paper _SHA
        s.insert_extraction(
            Overpotential(
                value=99.0, unit_label="mV",
                evidence=Evidence(
                    paper=Paper(sha256=other), page=1,
                    bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
                    parser_name="dots",
                ),
            ),
            run_id="r1",
        )
        return s

    monkeypatch.setattr(viewer_app, "_graph_store", _store)
    triples = client.get(f"/paper/{_SHA}/data").json()["triples"]
    assert len(triples) == 1
    assert triples[0]["value"] == 236.0  # _SHA's measurement, not the other's 99


def test_data_unknown_sha_returns_empty(monkeypatch):
    monkeypatch.setattr(viewer_app, "_graph_store", _store_with_one)
    other = "b" * 64
    r = client.get(f"/paper/{other}/data")
    assert r.status_code == 200
    assert r.json() == {"sha": other, "triples": []}


def test_data_rejects_non_hex_sha(monkeypatch):
    # `sha` is interpolated into a SPARQL IRI; a non-hex value must short-circuit
    # to [] rather than reach the query string.
    monkeypatch.setattr(viewer_app, "_graph_store", _store_with_one)
    r = client.get("/paper/not-a-sha/data")
    assert r.status_code == 200
    assert r.json()["triples"] == []
