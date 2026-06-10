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
    Electrolyte,
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
    # Concrete: 4 m-side (type, value, unit_label, condition-edge) + 4 paper-side
    # (type, sha256, identifier, name) + 2 PROV links (wasDerivedFrom,
    # wasGeneratedBy) + 9 activity-side (used, page, 4×bbox, parserName, runId,
    # sourceText) + 3 condition-side (type, currentDensity, temperatureC)
    # = 22 triples for the populated fixture. Pin the exact count so a regression
    # that silently omits a triple is caught loudly.
    # NOTE: was 18 before T46/C1; +4 are the now-persisted Condition triples
    # (the fixture carries current_density=10, temperature_C=25). Conditions used
    # to be dropped — see test_condition_written_to_graph.
    assert len(store) == 22


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


def test_condition_written_to_graph():
    """C1 (T46): a measurement's experimental conditions must land in the graph,
    not be dropped. An overpotential without its current density / temperature is
    not a comparable datum. The fixture carries current_density=10, temperature_C=25.
    """
    store = RDFStore()
    store.insert_extraction(_overpotential(), run_id="r1")

    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> "
        "SELECT ?cd ?t WHERE { "
        "?m palim:condition ?c . "
        "?c a palim:Condition ; palim:currentDensity ?cd ; palim:temperatureC ?t . }"
    )
    assert len(rows) == 1
    assert float(rows[0]["cd"]) == 10.0
    assert float(rows[0]["t"]) == 25.0


def test_electrolyte_written_to_graph():
    """C1 (T46): a Condition's electrolyte (formula, concentration, pH) is a
    sub-node and must also be persisted."""
    op = Overpotential(
        value=300.0,
        unit_label="mV",
        condition=Condition(
            current_density=10.0,
            electrolyte=Electrolyte(formula="KOH", concentration=1.0, electrolyte_ph=14.0),
        ),
        evidence=_evidence(),
    )
    store = RDFStore()
    store.insert_extraction(op, run_id="r1")

    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> "
        "SELECT ?f ?c ?ph WHERE { "
        "?m palim:condition ?cond . "
        "?cond palim:electrolyte ?e . "
        "?e a palim:Electrolyte ; palim:formula ?f ; "
        "palim:concentration ?c ; palim:electrolytePH ?ph . }"
    )
    assert len(rows) == 1
    assert rows[0]["f"] == "KOH"
    assert float(rows[0]["c"]) == 1.0
    assert float(rows[0]["ph"]) == 14.0


def test_no_condition_adds_no_condition_triples():
    """A measurement without a Condition must add zero condition triples
    (guard path). Baseline count stays at the pre-C1 18."""
    op = Overpotential(value=1.0, unit_label="mV", evidence=_evidence())
    store = RDFStore()
    store.insert_extraction(op, run_id="r1")

    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> SELECT ?c WHERE {{ ?m palim:condition ?c . }}"
    )
    assert rows == []
    assert len(store) == 18


def test_empty_condition_emits_no_edge():
    """A Condition with no populated fields is vacuous — skip it rather than
    writing a contentless blank node (and likewise an all-None Electrolyte)."""
    op = Overpotential(
        value=1.0, unit_label="mV", condition=Condition(), evidence=_evidence()
    )
    store = RDFStore()
    store.insert_extraction(op, run_id="r1")

    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> SELECT ?c WHERE {{ ?m palim:condition ?c . }}"
    )
    assert rows == []
    assert len(store) == 18


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
