"""T24 — RDF store: validated Pydantic Measurement → pyoxigraph triples + PROV-O provenance.

CLAUDE.md non-negotiable: every triple carries (paper_hash, parser, page, bbox,
run_id). Enforced here by refusing to insert any ``Measurement`` whose
``evidence`` is None.

**Signature deviation from T24 card (documented):** card prescribed
``insert_extraction(instance, paper_sha, page, bbox, parser_name, run_id,
source_text="")`` with provenance as explicit positional args. After T19's
audit + F4's bbox split, a validated Measurement instance ALREADY carries its
Evidence (all 7 provenance slots required by Pydantic), so re-passing them
duplicates work the caller already did. Slimmed to
``insert_extraction(instance, *, run_id, parse_run_id=None)`` — Evidence is
pulled from the instance; ``run_id`` and ``parse_run_id`` stay explicit
because they live outside the schema (CostMeter ledger concern per T24 card
line 16).

**Two run_ids, two predicates — in a named graph (T46b/C4 Option A):**
Run metadata is NOT a schema slot, so it would break the closed SHACL shapes if
placed on the measurement/Evidence nodes. It lives instead in a per-run named
graph ``palimpsest:run/<run_id>`` keyed to the measurement IRI, OUT of the
SHACL-validated default graph:
- ``palimpsest:runId`` = extraction run_id (the run that produced the triple).
- ``palimpsest:parseRunId`` (optional) = the parse run_id whose cached output
  this extraction read.
Both are recoverable per measurement via a ``GRAPH``-clause query on ``m_iri``;
reproducibility is CLAUDE.md-aligned (per-triple traceability beats
reconstructable) and the link is now a stable IRI, not an anonymous activity.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel
from pyoxigraph import (
    BlankNode,
    DefaultGraph,
    Literal,
    NamedNode,
    Quad,
    RdfFormat,
    Store,
    Variable,
)

PALIM = "https://w3id.org/palimpsest/"
PROV = "http://www.w3.org/ns/prov#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
SCHEMA_ORG = "http://schema.org/"
EMMO_ECHO = "https://w3id.org/emmo/domain/electrochemistry#"
XSD_FLOAT = NamedNode("http://www.w3.org/2001/XMLSchema#float")
XSD_INT = NamedNode("http://www.w3.org/2001/XMLSchema#integer")

# Slot URI prefix → expanded base. Mirrors `schema/generated/context.jsonld`
# but kept inline because pyoxigraph wants full IRIs, not CURIEs.
_PREFIX = {
    "emmo:": EMMO_ECHO,
    "palimpsest:": PALIM,
    "schema:": SCHEMA_ORG,
    "prov:": PROV,
}


def _expand(curie: str) -> str:
    for p, base in _PREFIX.items():
        if curie.startswith(p):
            return base + curie[len(p):]
    return curie  # already a full IRI


def _class_iri(instance: BaseModel) -> NamedNode:
    """Resolve the IRI for a Pydantic class via LinkML's ``class_uri`` meta.

    LinkML-generated classes carry a ``linkml_meta`` ClassVar (a Pydantic
    ``RootModel``); the ``class_uri`` CURIE lives at ``meta.root["class_uri"]``.
    Falls back to ``palimpsest:<ClassName>`` if the meta is missing — shouldn't
    happen, but stays loud at query time (wrong IRI → empty SPARQL rows) rather
    than silently minting a CURIE the schema doesn't declare.
    """
    meta = getattr(type(instance), "linkml_meta", None)
    if meta is not None and hasattr(meta, "root"):
        curie = meta.root.get("class_uri")
        if curie:
            return NamedNode(_expand(curie))
    return NamedNode(f"{PALIM}{type(instance).__name__}")


def _has_content(obj: BaseModel, table: tuple) -> bool:
    """True if any scalar slot in ``table`` is set on ``obj`` — used to skip
    writing a vacuous (all-None) Condition/Electrolyte node."""
    return any(getattr(obj, slot, None) is not None for slot, _, _ in table)


class RDFStore:
    """pyoxigraph store with provenance-anchored measurement insert.

    Default in-memory; pass a path to open a RocksDB store on disk.
    """

    def __init__(self, path: str | None = None) -> None:
        # `Store()` is in-memory; `Store(path)` opens RocksDB on disk.
        self._store: Store = Store(path) if path else Store()

    # --------------------------------------------------------------- insert

    def insert_extraction(
        self,
        instance: BaseModel,
        *,
        run_id: str,
        parse_run_id: str | None = None,
    ) -> str:
        """Insert one Measurement + provenance. Returns the measurement IRI.

        Raises ``ValueError`` if ``instance.evidence is None`` — CLAUDE.md
        provenance non-negotiable. Pre-T22 callers should never reach this
        path; T25 wires `validate_instance` ahead of this insert anyway.
        """
        ev = getattr(instance, "evidence", None)
        if ev is None:
            raise ValueError(
                f"refuse to insert {type(instance).__name__} without Evidence "
                "(CLAUDE.md provenance non-negotiable)"
            )

        m_iri = NamedNode(f"{PALIM}measurement/{uuid.uuid4()}")
        paper_iri = NamedNode(f"{PALIM}paper/{ev.paper.sha256}")
        evidence = BlankNode()

        # Measurement node — schema-shaped: value, unitLabel, condition (C1),
        # prov:hadPrimarySource → Evidence. Matches the closed SHACL shape so the
        # stored graph passes the same shapes validate_instance runs pre-insert
        # (T46b/C4); no stray prov:wasDerivedFrom / prov:wasGeneratedBy.
        self._add(m_iri, NamedNode(f"{RDF}type"), _class_iri(instance))
        if instance.value is not None:
            self._add(m_iri, NamedNode(f"{PALIM}value"),
                      Literal(str(instance.value), datatype=XSD_FLOAT))
        if instance.unit_label is not None:
            self._add(m_iri, NamedNode(f"{PALIM}unitLabel"),
                      Literal(instance.unit_label))
        self._add(m_iri, NamedNode(f"{PROV}hadPrimarySource"), evidence)

        # Evidence node (prov:Entity) — the source anchor, mirroring the closed
        # Evidence shape (paper, page, 4×bbox, parserName, sourceText).
        self._add(evidence, NamedNode(f"{RDF}type"), NamedNode(f"{PROV}Entity"))
        self._add(evidence, NamedNode(f"{PALIM}paper"), paper_iri)
        self._add(evidence, NamedNode(f"{PALIM}page"),
                  Literal(str(ev.page), datatype=XSD_INT))
        # F4: 4 typed per-corner bbox predicates (no dedup vulnerability)
        for slot, pred in (
            ("bbox_x0", "bboxX0"), ("bbox_y0", "bboxY0"),
            ("bbox_x1", "bboxX1"), ("bbox_y1", "bboxY1"),
        ):
            self._add(evidence, NamedNode(f"{PALIM}{pred}"),
                      Literal(str(getattr(ev, slot)), datatype=XSD_FLOAT))
        self._add(evidence, NamedNode(f"{PALIM}parserName"),
                  Literal(ev.parser_name))
        if ev.source_text:
            self._add(evidence, NamedNode(f"{PALIM}sourceText"),
                      Literal(ev.source_text))

        # Paper node (deduped on IRI; pyoxigraph store is set-semantic) ------
        self._add(paper_iri, NamedNode(f"{RDF}type"),
                  NamedNode(f"{SCHEMA_ORG}ScholarlyArticle"))
        self._add(paper_iri, NamedNode(f"{PALIM}sha256"),
                  Literal(ev.paper.sha256))
        if ev.paper.doi:
            self._add(paper_iri, NamedNode(f"{SCHEMA_ORG}identifier"),
                      Literal(ev.paper.doi))
        if ev.paper.title:
            self._add(paper_iri, NamedNode(f"{SCHEMA_ORG}name"),
                      Literal(ev.paper.title))

        # Run-provenance — per-run named graph keyed to the measurement IRI
        # (T46b/C4 Option A). run_id is not a schema slot; keeping it out of the
        # data graph preserves the closed-shape conformance above while staying
        # per-measurement recoverable via a GRAPH-clause query.
        run_graph = NamedNode(f"{PALIM}run/{run_id}")
        self._add(m_iri, NamedNode(f"{PALIM}runId"), Literal(run_id), run_graph)
        if parse_run_id is not None:
            self._add(m_iri, NamedNode(f"{PALIM}parseRunId"),
                      Literal(parse_run_id), run_graph)

        # Condition node (C1/T46) — experimental context; dropping it makes the
        # measurement uncomparable ("236 mV" means nothing without "at 10 mA/cm²").
        cond = getattr(instance, "condition", None)
        if cond is not None:
            self._add_condition(m_iri, cond)

        return m_iri.value

    # ------------------------------------------------------------- condition

    # (slot, predicate, datatype-or-None-for-plain-string)
    _COND_SCALARS = (
        ("current_density", "currentDensity", XSD_FLOAT),
        ("electrode_potential_vs_rhe", "potentialVsRHE", XSD_FLOAT),
        ("temperature_C", "temperatureC", XSD_FLOAT),
        ("scan_rate", "scanRate", XSD_FLOAT),
        ("cell_type", "cellType", None),
    )
    _ELECTROLYTE_SCALARS = (
        ("formula", "formula", None),
        ("concentration", "concentration", XSD_FLOAT),
        ("electrolyte_ph", "electrolytePH", XSD_FLOAT),
    )

    def _add_condition(self, m_iri: NamedNode, cond: BaseModel) -> None:
        """Attach a Condition node (and its Electrolyte sub-node) to a measurement.

        Predicates mirror the schema slot_uris (palimpsest:currentDensity, …) so
        the stored shape lines up with `schema/palimpsest.yaml`. Only set slots are
        emitted; absent optionals add no triples. A Condition (or Electrolyte) with
        no populated fields is vacuous and is skipped — no contentless blank node.
        """
        el = getattr(cond, "electrolyte", None)
        el_has = el is not None and _has_content(el, self._ELECTROLYTE_SCALARS)
        if not (_has_content(cond, self._COND_SCALARS) or el_has):
            return

        cond_iri = BlankNode()
        self._add(m_iri, NamedNode(f"{PALIM}condition"), cond_iri)
        self._add(cond_iri, NamedNode(f"{RDF}type"), _class_iri(cond))
        self._add_scalars(cond_iri, cond, self._COND_SCALARS)

        if el_has:
            el_iri = BlankNode()
            self._add(cond_iri, NamedNode(f"{PALIM}electrolyte"), el_iri)
            self._add(el_iri, NamedNode(f"{RDF}type"), _class_iri(el))
            self._add_scalars(el_iri, el, self._ELECTROLYTE_SCALARS)

    def _add_scalars(self, subj: BlankNode, obj: BaseModel,
                     table: tuple) -> None:
        for slot, pred, dt in table:
            val = getattr(obj, slot, None)
            if val is None:
                continue
            lit = Literal(str(val), datatype=dt) if dt else Literal(str(val))
            self._add(subj, NamedNode(f"{PALIM}{pred}"), lit)

    # ----------------------------------------------------------------- query

    def sparql(self, query: str) -> list[dict[str, Any]]:
        """Run a SELECT query; return rows as ``{var_name: literal_value}`` dicts.

        Plain str for literals (the ``.value`` accessor), the IRI for NamedNodes,
        the blank-node id for BlankNodes. UNBOUND bindings come back as None.
        """
        results = self._store.query(query)
        variables: list[Variable] = list(results.variables)
        out: list[dict[str, Any]] = []
        for sol in results:
            row: dict[str, Any] = {}
            for var in variables:
                term = sol[var]
                if term is None:
                    row[var.value] = None
                elif isinstance(term, Literal):
                    row[var.value] = term.value
                else:  # NamedNode, BlankNode
                    row[var.value] = term.value
            out.append(row)
        return out

    # --------------------------------------------------------------- helpers

    def __len__(self) -> int:
        return len(self._store)

    def dump_default_graph(self) -> bytes:
        """Serialize the default (data) graph as Turtle, excluding named graphs.

        Run-provenance lives in per-run named graphs (T46b/C4 Option A); this
        returns only the SHACL-validated data view.
        """
        return self._store.dump(format=RdfFormat.TURTLE, from_graph=DefaultGraph())

    def _add(self, s: Any, p: Any, o: Any, graph: Any = None) -> None:
        self._store.add(Quad(s, p, o) if graph is None else Quad(s, p, o, graph))
