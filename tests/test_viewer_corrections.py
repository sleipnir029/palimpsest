"""WS1 — viewer correction routes (POST /paper/{sha}/correct, GET .../corrections).

Mirrors test_viewer_data's in-memory store injection, but pins a SINGLE store
instance across calls (POST writes, GET reads — they must share state) and points
PALIMPSEST_WORKSPACE at tmp_path so the git/audit side effect stays isolated.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from schema.generated.pydantic import Evidence, Overpotential, Paper

from palimpsest.store import RDFStore
from palimpsest.viewer import app as viewer_app

client = TestClient(viewer_app.app)

_SHA = "a" * 64


def _seeded() -> RDFStore:
    s = RDFStore()
    s.insert_extraction(
        Overpotential(
            value=2360.0, unit_label="mV",
            evidence=Evidence(
                paper=Paper(sha256=_SHA), page=1,
                bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
                parser_name="docling",
            ),
        ),
        run_id="r1",
    )
    return s


def _pin_store(monkeypatch, tmp_path) -> RDFStore:
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    store = _seeded()
    monkeypatch.setattr(viewer_app, "_graph_store", lambda: store)
    return store


def test_correct_then_list_roundtrip(monkeypatch, tmp_path):
    _pin_store(monkeypatch, tmp_path)
    iri = client.get(f"/paper/{_SHA}/data").json()["triples"][0]["id"]

    res = client.post(f"/paper/{_SHA}/correct", json={
        "measurement_iri": iri,
        "comment": "should be 236 mV",
        "new_value": 236.0, "new_unit": "mV",
    })
    assert res.status_code == 200, res.text
    assert res.json()["prior_value"] == 2360.0

    # Original value is still served — append-only, the data graph was not mutated.
    assert client.get(f"/paper/{_SHA}/data").json()["triples"][0]["value"] == 2360.0

    corrs = client.get(f"/paper/{_SHA}/corrections").json()["corrections"]
    assert len(corrs) == 1
    assert corrs[0]["author"] == "human"
    assert corrs[0]["measurement_id"] == iri
    assert corrs[0]["prior_value"] == 2360.0
    assert corrs[0]["corrected_value"] == 236.0


def test_correct_unknown_measurement_422(monkeypatch, tmp_path):
    _pin_store(monkeypatch, tmp_path)
    res = client.post(f"/paper/{_SHA}/correct", json={
        "measurement_iri": "https://w3id.org/palimpsest/measurement/nope",
        "comment": "x", "new_value": 1.0,
    })
    assert res.status_code == 422


def test_correct_non_hex_sha_400(monkeypatch, tmp_path):
    _pin_store(monkeypatch, tmp_path)
    res = client.post("/paper/not-a-sha/correct", json={
        "measurement_iri": "x", "comment": "y", "new_value": 1.0,
    })
    assert res.status_code == 400


def test_correct_malformed_iri_422(monkeypatch, tmp_path):
    # A crafted measurement_iri must be a handled 422, not a 500 (review B1).
    _pin_store(monkeypatch, tmp_path)
    res = client.post(f"/paper/{_SHA}/correct", json={
        "measurement_iri": "x> } junk #", "comment": "y", "new_value": 1.0,
    })
    assert res.status_code == 422
