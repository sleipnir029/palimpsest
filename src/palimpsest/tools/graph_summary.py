"""`describe_schema` + `graph_summary` tools (T62) — the read side of the
run-time autonomy spine.

For the agent to "use the ontology to build the graph" without Claude Code
present, it must read the schema contract at run time. Today the schema reaches
the model only as a JSON blob silently embedded in the extraction prompt — the
agent *loop* never sees it. These two read-only tools surface it:

  * ``describe_schema()`` — the 9 Measurement classes, each with its type IRI
    (CURIE), canonical unit, and slots, plus the Condition context slots and the
    universal categorical enums. This is what the loop reads to build correct
    SPARQL and emit schema-valid extractions. Offline, no graph touched.
  * ``graph_summary()`` — what's actually in the live graph: per-type measurement
    counts, #papers, and coverage. Reuses ``RDFStore.sparql``.

Both are read-only, €0, and make no graph/ledger/data writes (``graph_summary``
opens the on-disk store read-only; a locked/absent store degrades gracefully).
``describe_schema`` reuses ``extract._CLASS_MAP``/``_MEASUREMENT_NAMES`` and
``normalize`` (UNIVERSAL_UNITS / UNIVERSAL_ENUMS); ``graph_summary`` reuses
``store._expand`` for the rdf:type→name reverse map.

Honest gap (DEVIATIONS 2026-06-19): the T62 card lists ``#catalysts`` for
``graph_summary``, but ``store.insert_extraction`` never persists a catalyst
node — only measurement / evidence / paper / condition / electrolyte. So the
catalyst count is reported as "not persisted" rather than fabricated.
"""

from __future__ import annotations

from . import register


def _class_curie(cls) -> str | None:
    """The ``class_uri`` CURIE from a LinkML-generated class's meta, or None.

    Same source ``store._class_iri`` reads, but kept as the CURIE so this tool
    stays lightweight (no pyoxigraph import) — and the CURIE is exactly what the
    agent writes into a SPARQL ``?m a <IRI>`` clause.
    """
    meta = getattr(cls, "linkml_meta", None)
    if meta is not None and hasattr(meta, "root"):
        return meta.root.get("class_uri")
    return None


@register("describe_schema", {
    "description": (
        "Describe the extraction schema the graph is built from, as RDF the agent "
        "can query: SPARQL prefixes, the measurement classes (rdf:type IRI + "
        "canonical unit), the Measurement/Condition/Electrolyte node predicates, "
        "and the categorical enums. Read this to build correct SPARQL and emit "
        "schema-valid data. Read-only, opens no store, costs nothing (€0)."
    ),
    "input_schema": {"type": "object", "properties": {}},
})
def describe_schema() -> str:
    # Lazy: pulls in schema.generated.pydantic via extract + the predicate tables
    # from store; deferred out of the tools/__init__ scan (sparql_query /
    # workspace_status convention). Importing store reads class attrs only — it
    # opens no graph.
    from palimpsest.normalize import UNIVERSAL_ENUMS, UNIVERSAL_UNITS, canonical_unit
    from palimpsest.store import _PREFIX
    from palimpsest.store import RDFStore as _S

    from .extract import _CLASS_MAP, _MEASUREMENT_NAMES

    lines = [
        f"schema — {len(_MEASUREMENT_NAMES)} measurement classes (read-only, €0)",
        "",
        "SPARQL prefixes:",
    ]
    for prefix, base in _PREFIX.items():
        lines.append(f"  PREFIX {prefix} <{base}>")

    # Measurement-node predicates are written inline by store.insert_extraction;
    # they are stable schema-level facts (kept in sync with store.py).
    lines += [
        "",
        "Every Measurement node carries these predicates (emit value in the "
        "canonical unit shown):",
        "  palimpsest:value (float) · palimpsest:unitLabel · "
        "palimpsest:condition → Condition · prov:hadPrimarySource → Evidence",
        "",
        "measurement classes (name · rdf:type · canonical unit):",
    ]
    for name in sorted(_MEASUREMENT_NAMES):
        curie = _class_curie(_CLASS_MAP[name]) or f"palimpsest:{name}"
        unit = canonical_unit(name) or "—"
        lines.append(f"  - {name}  a {curie}  unit: {unit}")

    # Condition + Electrolyte predicates come straight from store.py's scalar
    # tables so the CURIE the agent queries is exactly what was inserted (no
    # slot-name-vs-predicate drift). Each row annotates the source slot + its
    # unit (UNIVERSAL_UNITS) or permissible enum values (UNIVERSAL_ENUMS).
    def _annotate(slot: str, dt) -> str:
        if slot in UNIVERSAL_ENUMS:
            return f"enum: {' | '.join(UNIVERSAL_ENUMS[slot])}"
        unit = UNIVERSAL_UNITS.get(slot)
        if unit:
            return f"unit: {unit}"
        return "number" if dt is not None else "free text"  # dt is XSD_FLOAT/INT

    lines.append("")
    lines.append("Condition node predicates (?m palimpsest:condition ?c . ?c …):")
    for slot, pred, dt in _S._COND_SCALARS:
        lines.append(f"  - palimpsest:{pred}  (slot {slot}; {_annotate(slot, dt)})")

    lines.append("")
    lines.append("Electrolyte node predicates (?c palimpsest:electrolyte ?e . ?e …):")
    for slot, pred, dt in _S._ELECTROLYTE_SCALARS:
        lines.append(f"  - palimpsest:{pred}  (slot {slot}; {_annotate(slot, dt)})")

    return "\n".join(lines)


_TYPE_COUNTS = """
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?type (COUNT(?m) AS ?n) WHERE {
  ?m prov:hadPrimarySource ?e .
  ?m a ?type .
} GROUP BY ?type
"""

_PAPER_COUNT = """
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX palimpsest: <https://w3id.org/palimpsest/>
SELECT (COUNT(DISTINCT ?paper) AS ?n) WHERE {
  ?m prov:hadPrimarySource ?e .
  ?e palimpsest:paper ?paper .
}
"""


def _type_name_map() -> dict[str, str]:
    """Map a stored rdf:type IRI (expanded) → friendly class name.

    ECHO-bound classes (Overpotential, …) persist as opaque EMMO hash IRIs;
    palimpsest-local classes (TafelSlope, …) as palimpsest: IRIs. Build the
    reverse map from each Measurement subclass's class_uri CURIE, expanded the
    same way store.py does.
    """
    from palimpsest.store import _expand

    from .extract import _CLASS_MAP, _MEASUREMENT_NAMES

    out: dict[str, str] = {}
    for name in _MEASUREMENT_NAMES:
        curie = _class_curie(_CLASS_MAP[name]) or f"palimpsest:{name}"
        out[_expand(curie)] = name
    return out


@register("graph_summary", {
    "description": (
        "Summarise what's in the RDF graph: measurement counts per type, number "
        "of papers, and coverage (how many of the measurement types are present). "
        "Read-only over the live graph, no writes, costs nothing (€0)."
    ),
    "input_schema": {"type": "object", "properties": {}},
})
def graph_summary(*, store=None) -> str:
    from palimpsest.store import RDFStore

    from .extract import _MEASUREMENT_NAMES

    # A locked/absent on-disk store must not crash a read-only summary. Opening
    # RDFStore("store") takes an exclusive RocksDB lock and can raise, so the
    # construction itself is inside the try (not just the queries).
    try:
        store = store if store is not None else RDFStore("store")
        type_rows = store.sparql(_TYPE_COUNTS)
        paper_rows = store.sparql(_PAPER_COUNT)
    except Exception as exc:  # noqa: BLE001 — degrade gracefully, read-only tool
        return f"graph summary unavailable (store not readable: {exc})"

    name_map = _type_name_map()
    counts: dict[str, int] = {}
    for row in type_rows:
        iri = row.get("type")
        if iri is None:
            continue
        counts[name_map.get(iri, iri)] = int(row["n"])

    total = sum(counts.values())
    if total == 0:
        return "graph summary — no measurements in graph yet (read-only, €0)"

    n_papers = int(paper_rows[0]["n"]) if paper_rows and paper_rows[0].get("n") else 0

    lines = [
        f"graph summary — {total} measurements, {n_papers} papers (read-only, €0)",
        "",
        "by type:",
    ]
    for name in sorted(counts, key=lambda k: (-counts[k], k)):
        lines.append(f"  {name}: {counts[name]}")

    lines.append("")
    lines.append(f"papers: {n_papers} with measurements")
    lines.append(
        f"coverage: {len(counts)}/{len(_MEASUREMENT_NAMES)} measurement types present"
    )
    lines.append(
        "catalysts: not persisted to the graph (store.py inserts no catalyst node; "
        "see DEVIATIONS 2026-06-19)"
    )
    return "\n".join(lines)
