"""T24 — RDF store tests.

Covers:
- Insert one Overpotential: measurement node + Evidence node + Paper node land
  in the data graph; run-provenance lands in a per-run named graph.
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
    PEMWECellVoltage,
    Stability,
)

from palimpsest.store import PALIM, RDFStore


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

    # Exact count pins the whole quad set (data graph + run-provenance graph)
    # so a regression that silently omits a triple is caught loudly. Post-T46b
    # structure (21 data-graph + 1 run-graph = 22):
    #   5 measurement-side: type, value, unitLabel, condition-edge,
    #                       prov:hadPrimarySource-edge
    #   9 evidence-side:    type, paper-edge, page, 4×bbox, parserName, sourceText
    #   4 paper-side:       type, sha256, identifier, name
    #   3 condition-side:   type, currentDensity, temperatureC
    #   1 run-graph:        palimpsest:runId  (named graph palimpsest:run/r1)
    # (T46b moved provenance from a prov:wasGeneratedBy activity to an Evidence
    # node + a run-provenance named graph; the total is coincidentally still 22.)
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
    (guard path). Baseline: 4 measurement + 9 evidence + 4 paper + 1 run-graph
    = 18 (no condition node)."""
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


def _conforms(store: RDFStore) -> tuple[bool, str]:
    """Run the shipped SHACL shapes against the store's default (data) graph.

    The C4 acceptance bar: what is persisted must pass the same shapes that
    `validate_instance` runs pre-insert. Named graphs (run-provenance) are
    excluded by `dump_default_graph`, so only the data view is validated.
    """
    import pyshacl
    from rdflib import Graph as RDFGraph

    from palimpsest.validation import _shapes

    g = RDFGraph().parse(data=store.dump_default_graph().decode(), format="turtle")
    conforms, _, report = pyshacl.validate(g, shacl_graph=_shapes(), inference="none")
    return conforms, report


def test_stored_data_graph_conforms_to_shacl():
    """C4 (T46b): the persisted measurement subgraph must pass the shipped
    closed SHACL shapes — measurement via prov:hadPrimarySource→Evidence and
    palimpsest:condition→Condition, no stray prov:wasDerivedFrom/wasGeneratedBy.
    """
    store = RDFStore()
    store.insert_extraction(_overpotential(), run_id="r1")
    conforms, report = _conforms(store)
    assert conforms, report


def test_run_ids_in_named_graph():
    """C4/Option A: run_id and parse_run_id live in a per-run named graph keyed
    to the measurement IRI — out of the SHACL-validated data graph, but still
    recoverable per measurement via a GRAPH-clause query.
    """
    store = RDFStore()
    iri = store.insert_extraction(
        _overpotential(),
        run_id="extract-2026-06-08",
        parse_run_id="parse-2026-05-31",
    )

    # Subject must be the returned measurement IRI (the "keyed to the measurement
    # IRI" guarantee), not merely some node in some named graph.
    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> "
        "SELECT ?m ?rid ?prid WHERE { GRAPH ?g { "
        "?m palim:runId ?rid ; palim:parseRunId ?prid . } }"
    )
    assert rows == [
        {"m": iri, "rid": "extract-2026-06-08", "prid": "parse-2026-05-31"}
    ]


def test_confidence_written_when_set():
    """Per-value confidence (optional Measurement slot) persists as palim:confidence
    on the measurement node when the instance carries it."""
    op = Overpotential(value=236.0, unit_label="mV", confidence=0.92, evidence=_evidence())
    store = RDFStore()
    iri = store.insert_extraction(op, run_id="r1")
    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> "
        f"SELECT ?c WHERE {{ <{iri}> palim:confidence ?c . }}"
    )
    assert len(rows) == 1
    assert float(rows[0]["c"]) == 0.92


def test_no_confidence_adds_no_confidence_triple():
    """A measurement without confidence (legacy/untagged) still inserts and adds
    zero palim:confidence triples — the optional slot is skipped when None."""
    op = Overpotential(value=236.0, unit_label="mV", evidence=_evidence())
    store = RDFStore()
    iri = store.insert_extraction(op, run_id="r1")
    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> SELECT ?c WHERE {{ <{iri}> palim:confidence ?c . }}"
    )
    assert rows == []


def test_extraction_model_in_named_graph():
    """The extraction_model tag lands in the per-run named graph keyed to the
    measurement IRI (like runId) — out of the SHACL-validated data graph."""
    store = RDFStore()
    iri = store.insert_extraction(
        _overpotential(), run_id="r1", extraction_model="gemini-3.1-flash-lite (openrouter)"
    )
    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> "
        "SELECT ?m ?model WHERE { GRAPH ?g { ?m palim:extractionModel ?model . } }"
    )
    assert rows == [{"m": iri, "model": "gemini-3.1-flash-lite (openrouter)"}]


def test_no_extraction_model_adds_no_tag():
    """Omitting extraction_model (legacy/pipeline default) writes no tag triple."""
    store = RDFStore()
    store.insert_extraction(_overpotential(), run_id="r1")
    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> "
        "SELECT ?model WHERE { GRAPH ?g { ?m palim:extractionModel ?model . } }"
    )
    assert rows == []


@pytest.mark.parametrize("cls, unit", [
    (Overpotential, "mV"),
    (Stability, "h"),
    (PEMWECellVoltage, "V"),
])
def test_confidence_data_graph_conforms_to_shacl(cls, unit):
    """C4: confidence must pass the closed SHACL shape on EVERY Measurement
    subclass, not just the base — the closure is per-subclass-shape, so an
    Overpotential-only test would miss a subclass whose shape lacks confidence."""
    m = cls(value=1.0, unit_label=unit, confidence=0.88, evidence=_evidence())
    store = RDFStore()
    store.insert_extraction(m, run_id="r1")
    conforms, report = _conforms(store)
    assert conforms, report


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


def test_condition_enums_reach_graph():
    """T50: the universal categorical enums modeled on Condition (iR_correction
    etc.) must actually persist as triples — not just validate in Pydantic and
    get dropped at insertion. Stored as their bare permissible value, not
    "EnumName.member".
    """
    cond = Condition(
        current_density=10.0,
        iR_correction="applied",
        cell_type_family="RDE",
        scan_rate_regime="slow_LSV",
    )
    m = Overpotential(value=236.0, unit_label="mV", condition=cond, evidence=_evidence())
    store = RDFStore()
    store.insert_extraction(m, run_id="r1")
    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> "
        "SELECT ?ir ?fam ?reg WHERE { "
        "?c palim:iRCorrection ?ir ; palim:cellTypeFamily ?fam ; palim:scanRateRegime ?reg . }"
    )
    assert len(rows) == 1
    assert rows[0] == {"ir": "applied", "fam": "RDE", "reg": "slow_LSV"}


def test_t71_catalyst_loading_reaches_graph():
    """T71: the new catalyst_loading Condition slot must persist as a triple —
    the modeled-but-unpersisted trap (T50). Without the _COND_SCALARS row it
    would validate in Pydantic and be silently dropped at insertion.
    """
    cond = Condition(current_density=2000.0, temperature_C=80.0, catalyst_loading=0.15)
    m = PEMWECellVoltage(value=1.75, unit_label="V", condition=cond, evidence=_evidence())
    store = RDFStore()
    store.insert_extraction(m, run_id="r1")
    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> "
        "SELECT ?load WHERE { ?c palim:catalystLoading ?load . }"
    )
    assert len(rows) == 1
    assert float(rows[0]["load"]) == 0.15


def test_t71_pemwe_cell_voltage_inserts():
    """T71: a PEMWECellVoltage instance inserts like any Measurement (generic
    store path — no store.py per-class change needed)."""
    m = PEMWECellVoltage(
        value=1.75, unit_label="V",
        condition=Condition(current_density=2000.0),
        evidence=_evidence(),
    )
    store = RDFStore()
    iri = store.insert_extraction(m, run_id="r1")
    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> SELECT ?v WHERE {{ <{iri}> palim:value ?v . }}"
    )
    assert len(rows) == 1
    assert float(rows[0]["v"]) == 1.75
