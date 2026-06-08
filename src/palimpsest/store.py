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

**Two run_ids, two predicates (card line 16 decision):**
- ``palimpsest:runId`` = extraction run_id (the PROV-O ``prov:wasGeneratedBy``
  activity that produced the triple).
- ``palimpsest:parseRunId`` (optional) = the parse run_id whose cached output
  this extraction read. Stored separately so a parse → triple chain is
  recoverable without joining through ``parser_runs``; reproducibility is
  CLAUDE.md-aligned (per-triple traceability beats reconstructable).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel
from pyoxigraph import BlankNode, Literal, NamedNode, Quad, Store, Variable

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
        activity = BlankNode()

        # Measurement node ----------------------------------------------------
        self._add(m_iri, NamedNode(f"{RDF}type"), _class_iri(instance))
        if instance.value is not None:
            self._add(m_iri, NamedNode(f"{PALIM}value"),
                      Literal(str(instance.value), datatype=XSD_FLOAT))
        if instance.unit_label is not None:
            self._add(m_iri, NamedNode(f"{PALIM}unitLabel"),
                      Literal(instance.unit_label))

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

        # PROV-O links --------------------------------------------------------
        self._add(m_iri, NamedNode(f"{PROV}wasDerivedFrom"), paper_iri)
        self._add(m_iri, NamedNode(f"{PROV}wasGeneratedBy"), activity)
        self._add(activity, NamedNode(f"{PROV}used"), paper_iri)
        self._add(activity, NamedNode(f"{PALIM}page"),
                  Literal(str(ev.page), datatype=XSD_INT))
        # F4: 4 typed per-corner bbox predicates (no dedup vulnerability)
        for slot, pred in (
            ("bbox_x0", "bboxX0"), ("bbox_y0", "bboxY0"),
            ("bbox_x1", "bboxX1"), ("bbox_y1", "bboxY1"),
        ):
            self._add(activity, NamedNode(f"{PALIM}{pred}"),
                      Literal(str(getattr(ev, slot)), datatype=XSD_FLOAT))
        self._add(activity, NamedNode(f"{PALIM}parserName"),
                  Literal(ev.parser_name))
        self._add(activity, NamedNode(f"{PALIM}runId"), Literal(run_id))
        if parse_run_id is not None:
            self._add(activity, NamedNode(f"{PALIM}parseRunId"),
                      Literal(parse_run_id))
        if ev.source_text:
            self._add(activity, NamedNode(f"{PALIM}sourceText"),
                      Literal(ev.source_text))

        return m_iri.value

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

    def _add(self, s: Any, p: Any, o: Any) -> None:
        self._store.add(Quad(s, p, o))
