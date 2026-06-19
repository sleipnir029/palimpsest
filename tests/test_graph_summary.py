"""T62 — describe_schema / graph_summary tests.

The read side of the run-time autonomy spine: the agent must be able to read the
schema contract (classes/slots/units) and summarise the live graph at run time,
without Claude Code present.

Covers:
- describe_schema lists the 9 Measurement classes, each with its canonical unit
  and slots, plus the Condition context slots (all offline — no graph needed).
- graph_summary over a seeded in-memory store: per-type counts + #papers, with
  both an EMMO-typed class (Overpotential) and a palimpsest-local class
  (TafelSlope) so the rdf:type→name reverse-map is exercised.
- graph_summary on an empty graph degrades to a graceful no-measurements message.
"""

from __future__ import annotations

from schema.generated.pydantic import Evidence, Overpotential, Paper, TafelSlope

from palimpsest.store import RDFStore
from palimpsest.tools.graph_summary import describe_schema, graph_summary

# The 9 Measurement subclasses (T18 + T52's SpecificActivity/Stability).
_NINE = {
    "Overpotential",
    "TafelSlope",
    "ExchangeCurrentDensity",
    "ChargeTransferCoefficient",
    "MassActivity",
    "TurnoverFrequency",
    "ECSA",
    "SpecificActivity",
    "Stability",
}


def _evidence(sha: str) -> Evidence:
    return Evidence(
        paper=Paper(sha256=sha, doi="10.1000/xyz", title="A paper"),
        page=1,
        bbox_x0=0.1, bbox_y0=0.2, bbox_x1=0.3, bbox_y1=0.4,
        parser_name="mineru",
        source_text="η = 236 mV at 10 mA/cm²",
    )


# ----------------------------------------------------------- describe_schema


def test_describe_schema_lists_nine_measurement_classes():
    out = describe_schema()
    for name in _NINE:
        assert name in out, f"{name} missing from describe_schema output"


def test_describe_schema_surfaces_canonical_units():
    out = describe_schema()
    assert "mV" in out                      # Overpotential's unit
    assert "mV/decade" in out               # TafelSlope's unit


def test_describe_schema_surfaces_rdf_predicates_for_sparql():
    """The autonomy-critical half: the agent must get the actual RDF *predicates*
    (not Python slot names) to build a query that returns rows. Predicates are
    sourced from store.py so they cannot drift."""
    out = describe_schema()
    # Measurement-node predicates (store.insert_extraction).
    assert "palimpsest:value" in out
    assert "palimpsest:unitLabel" in out
    assert "palimpsest:condition" in out
    assert "prov:hadPrimarySource" in out
    # Condition-node predicates (store._COND_SCALARS), incl. an enum predicate.
    assert "palimpsest:currentDensity" in out
    assert "palimpsest:potentialVsRHE" in out   # slot electrode_potential_vs_rhe
    assert "palimpsest:cellType" in out         # was dropped before (no unit)
    assert "palimpsest:iRCorrection" in out     # enum slot
    # Prefix bases so a CURIE can be expanded.
    assert "https://w3id.org/palimpsest/" in out
    assert "https://w3id.org/emmo/domain/electrochemistry#" in out


def test_describe_schema_puts_electrolyte_ph_under_electrolyte_not_condition():
    """electrolyte_ph lives on the Electrolyte sub-node
    (?c palimpsest:electrolyte ?e . ?e palimpsest:electrolytePH), NOT flat on
    Condition — querying it as a Condition predicate returns zero rows."""
    out = describe_schema()
    assert "palimpsest:electrolyte " in out     # the Condition→Electrolyte edge
    assert "palimpsest:electrolytePH" in out
    # the pH predicate appears after the Electrolyte section begins, not in the
    # Condition section.
    assert out.index("Electrolyte") < out.index("palimpsest:electrolytePH")


def test_describe_schema_marks_numeric_predicates_as_numbers():
    """A float-typed predicate without a fixed unit (e.g. electrolyte
    concentration) must read as numeric, not 'free text' — else the agent quotes
    a number in SPARQL."""
    out = describe_schema()
    conc_line = next(ln for ln in out.splitlines() if "palimpsest:concentration" in ln)
    assert "free text" not in conc_line
    assert "number" in conc_line


# ------------------------------------------------------------- graph_summary


def test_graph_summary_per_type_counts():
    store = RDFStore()
    # 2 Overpotentials in paper aaa, 1 TafelSlope in paper bbb.
    store.insert_extraction(
        Overpotential(value=236.0, unit_label="mV", evidence=_evidence("aaa")),
        run_id="r1",
    )
    store.insert_extraction(
        Overpotential(value=298.0, unit_label="mV", evidence=_evidence("aaa")),
        run_id="r1",
    )
    store.insert_extraction(
        TafelSlope(value=52.6, unit_label="mV/decade", evidence=_evidence("bbb")),
        run_id="r1",
    )

    out = graph_summary(store=store)
    assert "Overpotential: 2" in out
    assert "TafelSlope: 1" in out
    assert "papers: 2" in out
    # The prov:hadPrimarySource anchor must exclude non-measurement nodes from
    # the type counts — Paper/Evidence/Condition must never appear as a "type".
    assert "Paper" not in out and "Evidence" not in out
    assert "3 measurements" in out  # exactly the 3 inserted, nothing extra


def test_graph_summary_empty_graph_is_graceful():
    out = graph_summary(store=RDFStore())
    assert "no measurements" in out.lower()


def test_graph_summary_degrades_on_unreadable_store():
    """A locked/absent store must not crash a read-only summary."""
    class _Unreadable:
        def sparql(self, query):
            raise OSError("store locked")

    out = graph_summary(store=_Unreadable())
    assert "unavailable" in out.lower()


def test_graph_summary_degrades_when_store_construction_fails(monkeypatch):
    """The real lock case: opening RDFStore('store') takes an exclusive RocksDB
    lock and can raise *at construction*. That must degrade too — guards the
    construction-inside-try fix."""
    import palimpsest.store as store_mod

    class _Boom:
        def __init__(self, *a, **k):
            raise OSError("store locked")

    monkeypatch.setattr(store_mod, "RDFStore", _Boom)
    out = graph_summary()  # no store= → constructs RDFStore("store")
    assert "unavailable" in out.lower()
