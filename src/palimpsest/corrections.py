"""Append-only superseding corrections (WS1) — the shared human+agent correction path.

A correction never mutates or deletes the original extraction. It appends a new
``palimpsest:Correction`` node into a dedicated corrections named graph
(``palimpsest:corrections/<run_id>``) that *supersedes* the original measurement
via ``prov:wasRevisionOf``. The original triple in the SHACL-validated default
graph is untouched, so the data view (``/paper/{sha}/data``) still returns it and
the full edit history is recoverable. The same record doubles as feedback:
accumulated corrections are labeled extractor errors, queryable by SPARQL to score
the extractor and, on user request, to guide a re-extraction (T84/T74/T35).

This is a deliberate, *isolated* second write path to the graph (the first being
the pipeline's ``store.insert_extraction``). It does NOT expose a general
set-triple capability: it only appends a Correction node, only into the
corrections graph, and it mirrors the pipeline's provenance guard — it refuses to
record a correction against a measurement that carries no Evidence anchor
(CLAUDE.md non-negotiable). It reuses the private ``RDFStore._add`` on purpose,
rather than widening ``RDFStore``'s public write surface into a general writer.

Two front doors call this one function:
- the viewer's ``POST /paper/{sha}/correct`` (``author="human"``), which passes its
  already-open RocksDB store — RocksDB is single-writer, so opening a second handle
  while the viewer is up would deadlock (see ``viewer.app._graph_store``);
- the agent's ``correct_measurement`` tool (``author="palimpsest-agent"``), which
  opens its own store (the viewer must be stopped, same rule as ``extract_paper``).

Vocabulary (``palimpsest:Correction`` + slots, ``prov:wasRevisionOf`` /
``prov:generatedAtTime``) is declared in ``schema/exploratory.yaml`` — the
exploratory layer, never the closed main schema.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from pyoxigraph import Literal, NamedNode

from . import versioning
from .policy import workspace_root
from .store import PALIM, PROV, RDF, XSD_FLOAT, RDFStore

XSD_DATETIME = NamedNode("http://www.w3.org/2001/XMLSchema#dateTime")
XSD_BOOLEAN = NamedNode("http://www.w3.org/2001/XMLSchema#boolean")


class CorrectionError(Exception):
    """A correction could not be recorded (no such measurement, no Evidence, or empty edit)."""


@dataclass
class CorrectionResult:
    """What a correction wrote — returned to the viewer response / agent tool."""

    correction_iri: str
    run_id: str
    paper_sha: str
    prior_value: float | None
    prior_unit: str | None
    commit_sha: str | None


# Read the original's current value/unit + its paper sha, anchored on Evidence.
# No rows ⇒ the IRI is not a provenance-anchored measurement ⇒ refuse (this is the
# corrections-side mirror of store.insert_extraction's evidence guard).
_PRIOR_QUERY = """\
PREFIX palim: <{palim}>
PREFIX prov: <{prov}>
SELECT ?value ?unit ?sha WHERE {{
  <{m}> prov:hadPrimarySource ?ev .
  ?ev palim:paper ?paper .
  ?paper palim:sha256 ?sha .
  OPTIONAL {{ <{m}> palim:value ?value }}
  OPTIONAL {{ <{m}> palim:unitLabel ?unit }}
}}"""


def correct_measurement(
    store: RDFStore,
    *,
    measurement_iri: str,
    comment: str,
    author: str,
    new_value: float | None = None,
    new_unit: str | None = None,
    flagged_wrong: bool = False,
    correction_run_id: str | None = None,
) -> CorrectionResult:
    """Record an append-only superseding correction; return what was written.

    ``store`` is passed in (NOT opened here) so the viewer can hand over its live,
    lock-holding RocksDB instance while the agent tool opens its own.

    Raises ``CorrectionError`` when the comment is empty, the edit is a no-op (no
    value/unit/flag), or the measurement has no Evidence anchor.
    """
    comment = comment.strip()
    if not comment:
        raise CorrectionError("a correction needs a comment (it becomes the git title + body)")
    if new_value is None and new_unit is None and not flagged_wrong:
        raise CorrectionError("empty correction: set new_value, new_unit, or flagged_wrong")

    # measurement_iri comes from an untrusted source (viewer POST body / agent input)
    # and is interpolated into a SPARQL <...>. Validate it as an IRI up front so a
    # malformed value becomes a handled CorrectionError (422 / refusal) instead of an
    # un-parseable query or NamedNode ValueError surfacing as a 500 / raw traceback.
    try:
        measurement_node = NamedNode(measurement_iri)
    except ValueError as exc:
        raise CorrectionError(f"not a valid measurement IRI: {measurement_iri!r}") from exc

    rows = store.sparql(_PRIOR_QUERY.format(palim=PALIM, prov=PROV, m=measurement_node.value))
    if not rows:
        raise CorrectionError(
            f"no provenance-anchored measurement at {measurement_iri!r} — refuse to "
            "correct (CLAUDE.md provenance non-negotiable)"
        )
    prior = rows[0]
    prior_value = float(prior["value"]) if prior["value"] is not None else None
    prior_unit = prior["unit"]
    paper_sha = prior["sha"]

    run_id = correction_run_id or f"correct-{uuid.uuid4()}"
    at = datetime.now(timezone.utc).isoformat()
    corr_graph = NamedNode(f"{PALIM}corrections/{run_id}")
    c_iri = NamedNode(f"{PALIM}correction/{uuid.uuid4()}")

    # Reuse the store's private quad writer (same package) — deliberately NOT a new
    # public writer, so RDFStore exposes no general set-triple hole. Everything lands
    # in corr_graph; the default (SHACL-validated) graph is never written here.
    def add(predicate: str, obj) -> None:
        store._add(c_iri, NamedNode(predicate), obj, corr_graph)

    add(f"{RDF}type", NamedNode(f"{PALIM}Correction"))
    add(f"{PROV}wasRevisionOf", measurement_node)  # superseding link
    add(f"{PALIM}paper", NamedNode(f"{PALIM}paper/{paper_sha}"))
    add(f"{PALIM}correctionAuthor", Literal(author))
    add(f"{PALIM}correctionComment", Literal(comment))
    add(f"{PALIM}correctionRunId", Literal(run_id))
    add(f"{PROV}generatedAtTime", Literal(at, datatype=XSD_DATETIME))
    if prior_value is not None:
        add(f"{PALIM}priorValue", Literal(str(prior_value), datatype=XSD_FLOAT))
    if prior_unit is not None:
        add(f"{PALIM}priorUnit", Literal(prior_unit))
    if new_value is not None:
        add(f"{PALIM}correctedValue", Literal(str(new_value), datatype=XSD_FLOAT))
    if new_unit is not None:
        add(f"{PALIM}correctedUnit", Literal(new_unit))
    if flagged_wrong:
        add(f"{PALIM}flaggedWrong", Literal("true", datatype=XSD_BOOLEAN))

    commit_sha = _commit_audit(
        run_id=run_id,
        comment=comment,
        record={
            "correction_iri": c_iri.value,
            "measurement_iri": measurement_iri,
            "paper_sha": paper_sha,
            "author": author,
            "comment": comment,
            "prior_value": prior_value,
            "prior_unit": prior_unit,
            "corrected_value": new_value,
            "corrected_unit": new_unit,
            "flagged_wrong": flagged_wrong,
            "generated_at": at,
        },
    )

    return CorrectionResult(
        correction_iri=c_iri.value,
        run_id=run_id,
        paper_sha=paper_sha,
        prior_value=prior_value,
        prior_unit=prior_unit,
        commit_sha=commit_sha,
    )


def _commit_audit(*, run_id: str, comment: str, record: dict) -> str | None:
    """Write the per-correction audit JSON into the workspace and git-commit it.

    ``store/`` is gitignored (RocksDB is bulk binary state), so the graph itself
    isn't committable; the audit JSON is the human-diffable, replayable record of
    the correction, committed with the comment as title + body.

    Best-effort, by design: the RDF correction is ALREADY written (the graph is the
    source of truth) by the time we get here, so an audit/git failure — no
    workspace, no git, disk full — returns ``None`` rather than aborting the
    correction after the durable write. Caveat: ``checkpoint`` commits the WHOLE
    workspace (``git add -A``), so any other uncommitted change is swept into this
    ``correct:`` commit; both front doors normally run on a clean workspace.
    """
    try:
        root = workspace_root()
        versioning.ensure_repo(root)
        corrections_dir = root / "corrections"
        corrections_dir.mkdir(parents=True, exist_ok=True)
        (corrections_dir / f"{run_id}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )
        title = comment.splitlines()[0][:60]
        return versioning.checkpoint(f"correct: {title}", body=comment)
    except Exception:
        return None
