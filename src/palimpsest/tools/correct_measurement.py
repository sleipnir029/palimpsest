"""`correct_measurement` tool — record an append-only correction to an extracted value.

The agent half of the shared correction path (``corrections.correct_measurement``):
on the user's request it fixes a wrong value/unit, or flags a measurement wrong,
keeping the original. Opens its own ``RDFStore`` — RocksDB is single-writer, so the
viewer must be stopped (same rule as ``extract_paper``). Author is recorded as the
agent; a human edit through the viewer records ``author="human"`` via the same
primitive, so both front doors produce identical, queryable correction records.
"""

from __future__ import annotations

from . import register


@register("correct_measurement", {
    "description": (
        "Record an append-only correction to a previously extracted measurement. "
        "Writes a superseding correction record (the original is never deleted) into "
        "the corrections graph with full provenance — author, prior value, comment, "
        "timestamp — and makes a git commit titled from the comment. Use when the "
        "user reports a wrong value/unit, or to flag an extraction as wrong. "
        "Accumulated corrections are labeled extractor errors, queryable via "
        "sparql_query. Requires the viewer to be stopped (single-writer store, like "
        "extract_paper)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "measurement_iri": {
                "type": "string",
                "description": "The measurement IRI (the 'id' from the viewer's /paper/{sha}/data) to correct.",
            },
            "comment": {
                "type": "string",
                "description": "Why it's wrong / what the right value is. Becomes the git commit title + body.",
            },
            "new_value": {"type": "number", "description": "Replacement numeric value."},
            "new_unit": {"type": "string", "description": "Replacement unit label."},
            "flagged_wrong": {
                "type": "boolean",
                "description": "Mark the extraction wrong with no replacement value.",
            },
        },
        "required": ["measurement_iri", "comment"],
    },
})
def correct_measurement(
    measurement_iri: str,
    comment: str,
    new_value: float | None = None,
    new_unit: str | None = None,
    flagged_wrong: bool = False,
) -> str:
    # Lazy import: store.py pulls in pyoxigraph + the generated schema; defer that
    # out of the tools/__init__ scan until the agent actually corrects something.
    from palimpsest.corrections import CorrectionError, correct_measurement as _correct
    from palimpsest.store import RDFStore

    try:
        r = _correct(
            RDFStore("store"),
            measurement_iri=measurement_iri,
            comment=comment,
            author="palimpsest-agent",
            new_value=new_value,
            new_unit=new_unit,
            flagged_wrong=flagged_wrong,
        )
    except CorrectionError as exc:
        return f"correction refused: {exc}"

    prior = (
        f"prior={r.prior_value}{(' ' + r.prior_unit) if r.prior_unit else ''}"
        if r.prior_value is not None
        else "flagged"
    )
    commit = f"; commit {r.commit_sha[:8]}" if r.commit_sha else ""
    return f"recorded correction {r.correction_iri} ({prior}){commit}"
