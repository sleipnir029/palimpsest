"""Provenance-join demo over the on-disk RDF graph (€0, read-only).

Shows the two things the graph does that a flat table can't without denormalizing
away provenance, over the on-disk ``store/`` (RocksDB is single-writer, so stop
the viewer first — this script opens the same store the viewer holds a lock on):

  A. cross-parser AGREEMENT per overpotential value — how many of the four
     parsers surfaced each number (a live validity signal; a value only one
     parser reaches is the parser-conditional H3 story, queryable).
  B. a cross-GRAPH join — value + parser live in the data graph, the LLM that
     produced the triple lives in a per-run named graph; one query joins them
     via a GRAPH clause. That is graph-native provenance.

This is a thesis/demo artifact (supervisor Q: "a competency question a table
can't answer"). It reads only; it inserts nothing and spends nothing. Numbers
here are a benchmarking dump (every model x parser insert), so 4-parser
agreement means "all four parser texts yielded it across runs" — a robustness
signal, NOT a claim each value is verified gold (correctness is rescore.py).

Run:  pixi run python experiments/store_provenance_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from palimpsest.store import RDFStore

_STORE = Path(__file__).resolve().parent.parent / "store"

# Overpotential is the one metric anchored to an EMMO ECHO class IRI (the rest
# are palimpsest-local where ECHO has a gap) — see schema/palimpsest.yaml.
_OVP = ("https://w3id.org/emmo/domain/electrochemistry#"
        "electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6")

_AGREEMENT = f"""
PREFIX palimpsest: <https://w3id.org/palimpsest/>
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?value (COUNT(DISTINCT ?parser) AS ?n_parsers)
       (GROUP_CONCAT(DISTINCT ?parser; SEPARATOR=", ") AS ?parsers) WHERE {{
  ?m a <{_OVP}> ; palimpsest:value ?value ; prov:hadPrimarySource ?ev .
  ?ev palimpsest:parserName ?parser .
}} GROUP BY ?value ORDER BY DESC(?n_parsers) ?value
"""

_CROSS_GRAPH = f"""
PREFIX palimpsest: <https://w3id.org/palimpsest/>
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?value ?parser ?model WHERE {{
  ?m a <{_OVP}> ; palimpsest:value ?value ; prov:hadPrimarySource ?ev .
  ?ev palimpsest:parserName ?parser .
  GRAPH ?g {{ ?m palimpsest:extractionModel ?model }}
}} ORDER BY ?value
"""


def main() -> None:
    if not _STORE.exists():
        sys.exit(f"no store at {_STORE} — run the pipeline first (see SETUP.md)")

    try:
        store = RDFStore(str(_STORE))  # RocksDB exclusive lock — mirrors graph_summary
    except Exception as exc:
        sys.exit(f"cannot open {_STORE} (locked? stop the viewer first): {exc}")
    print(f"TOTAL QUADS: {len(store)}")

    agreement = store.sparql(_AGREEMENT)
    print("\n=== A. overpotential values: how many parsers agree ===")
    for r in agreement:
        print(f"  {float(r['value']):>7.1f} mV | {r['n_parsers']} parsers: {r['parsers']}")

    cross = store.sparql(_CROSS_GRAPH)
    print("\n=== B. cross-graph join: value + parser + LLM (named run graph) ===")
    for r in cross[:12]:
        print(f"  {float(r['value']):>7.1f} mV | {r['parser']:<10} | {r['model']}")
    print(f"  …({len(cross)} rows total)")

    # Self-check: the demo is only meaningful if both provenance joins bind. A
    # parser rename or an empty store would silently print nothing otherwise.
    assert agreement, "agreement query returned no rows — empty/renamed store?"
    assert cross, "cross-graph join returned no rows — extractionModel missing?"
    print("\nOK — both provenance joins bound.")


if __name__ == "__main__":
    main()
