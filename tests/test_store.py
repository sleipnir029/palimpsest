"""T24 — RDF store tests.

Covers:
- Insert one Overpotential: measurement node + paper node + activity triples
  land; provenance non-negotiable expressed (≥10 provenance-side triples).
- SPARQL roundtrip for the inserted value.
- Refusal to insert a measurement without Evidence (CLAUDE.md).
- Two-run_id handling: parse_run_id stored separately when provided.
- RocksDB-on-disk path round-trips through tmp_path.
"""

from __future__ import annotations

import pytest

from schema.generated.pydantic import (
    Condition,
    Evidence,
    Overpotential,
    Paper,
)

from palimpsest.store import PALIM, PROV, RDFStore


def _evidence() -> Evidence:
    return Evidence(
        paper=Paper(sha256="abc123", doi="10.1000/xyz", title="A paper"),
        page=3,
        bbox_x0=0.1, bbox_y0=0.2, bbox_x1=0.3, bbox_y1=0.4,
        parser_name="mineru",
        source_text="η = 236 mV at 10 mA/cm²",
    )


def _overpotential() -> Overpotential:
    return Overpotential(
        value=236.0,
        unit_label="mV",
        condition=Condition(current_density=10.0, temperature_C=25.0),
        evidence=_evidence(),
    )


def test_insert_yields_measurement_and_provenance():
    store = RDFStore()
    iri = store.insert_extraction(_overpotential(), run_id="r1")
    assert iri.startswith(f"{PALIM}measurement/")

    # Per-card expectation: ≥1 measurement triple + ≥5 provenance triples.
    # Concrete: 3 m-side (type, value, unit_label) + 4 paper-side (type,
    # sha256, identifier, name) + 2 PROV links (wasDerivedFrom, wasGeneratedBy)
    # + 9 activity-side (used, page, 4×bbox, parserName, runId, sourceText)
    # = 18 triples for the populated fixture.
    assert len(store) >= 15


def test_sparql_roundtrips_value():
    store = RDFStore()
    store.insert_extraction(_overpotential(), run_id="r1")

    # Use the EMMO IRI for Overpotential (matches the schema's class_uri).
    rows = store.sparql(
        "PREFIX palim: <https://w3id.org/palimpsest/> "
        "PREFIX emmo: <https://w3id.org/emmo/domain/electrochemistry#> "
        "SELECT ?v WHERE { "
        "?m a emmo:electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6 ; "
        "palim:value ?v . }"
    )
    # pyoxigraph canonicalizes xsd:float literals ("236.0" → "236"); assert
    # numerically rather than pinning the textual form.
    assert len(rows) == 1
    assert float(rows[0]["v"]) == 236.0


def test_refuses_without_evidence():
    """CLAUDE.md non-negotiable: no triples without provenance."""
    store = RDFStore()
    op_no_ev = Overpotential(value=1.0, unit_label="mV")
    with pytest.raises(ValueError, match="without Evidence"):
        store.insert_extraction(op_no_ev, run_id="r1")
    assert len(store) == 0


def test_two_run_ids_distinct_predicates():
    """Extraction run_id and parse_run_id land on separate predicates so
    the parse → triple chain is recoverable without joining parser_runs.
    """
    store = RDFStore()
    store.insert_extraction(
        _overpotential(),
        run_id="extract-2026-06-08",
        parse_run_id="parse-2026-05-31",
    )

    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> "
        f"PREFIX prov: <{PROV}> "
        "SELECT ?rid ?prid WHERE { "
        "?m prov:wasGeneratedBy ?a . "
        "?a palim:runId ?rid ; palim:parseRunId ?prid . }"
    )
    assert rows == [{"rid": "extract-2026-06-08", "prid": "parse-2026-05-31"}]


def test_rocksdb_path_persists(tmp_path):
    """Store opened with an explicit path is a RocksDB store; triples survive
    close + reopen. Belt-and-suspenders against an accidental in-memory regression.
    """
    db = tmp_path / "store"
    s1 = RDFStore(str(db))
    s1.insert_extraction(_overpotential(), run_id="r1")
    initial_len = len(s1)
    del s1  # release the RocksDB lock

    s2 = RDFStore(str(db))
    assert len(s2) == initial_len
    rows = s2.sparql(
        f"PREFIX palim: <{PALIM}> "
        "SELECT ?v WHERE { ?m palim:value ?v . }"
    )
    assert len(rows) == 1
    assert float(rows[0]["v"]) == 236.0
