"""`extraction_report` tool (T58) — surface dropped measurements + reasons.

The trust gap T57 left open: ``workspace_status`` shows "N found · M inserted ·
K dropped", but not *why* the K dropped. The reasons were computed by ``extract``
(mis-citation guard, unit mismatch, missing evidence, unknown class, Pydantic
error) and ``run_paper`` (SHACL violations, insert refusals) — and, since T58,
persisted alongside the counts as ``errors_json`` on the ``extraction_runs`` row.

This tool reads the latest run for one (paper, parser) and lists each dropped
item with its reason. Read-only, no LLM, no GPU, €0 — constructing the run log
runs a ``CREATE TABLE IF NOT EXISTS`` on first use (the same DDL-on-construct as
ParserCache / CostMeter), but writes no rows.
"""

from __future__ import annotations

import json
import string

from . import register


@register("extraction_report", {
    "description": (
        "Show which extracted measurements were dropped and WHY, for the latest "
        "run of one paper under one parser. Reads the persisted drop reasons "
        "(mis-citation, unit mismatch, missing evidence, SHACL/insert refusal). "
        "Read-only, costs nothing (€0). Use after workspace_status to investigate "
        "a paper whose found-vs-inserted counts don't match."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "paper": {
                "type": "string",
                "description": "A PDF path or a 64-hex sha256 of the paper.",
            },
            "parser": {
                "type": "string",
                "description": "Parser whose run to report (default 'mineru').",
            },
        },
        "required": ["paper"],
    },
})
def extraction_report(paper: str, parser: str = "mineru", *, run_log=None) -> str:
    # Lazy import: runs.py is cheap, but keep the tools/__init__ scan free of it
    # (sparql_query / workspace_status convention).
    from palimpsest.runs import ExtractionRunLog

    run_log = run_log if run_log is not None else ExtractionRunLog()
    sha = _resolve_sha(paper)

    run = run_log.latest_run(sha, parser)
    if run is None:
        return (
            f"no extraction run recorded for paper {sha[:8]} under parser "
            f"'{parser}' — run the pipeline first"
        )

    found = run["n_extracted"] + run["n_errors"]   # candidates the LLM produced
    dropped = found - run["n_inserted"]            # never reached the graph
    # Same vocabulary as workspace_status ("N found · M inserted · K dropped").
    head = (
        f"{parser} · paper {sha[:8]}: {found} found, "
        f"{run['n_inserted']} inserted, {dropped} dropped"
    )

    reasons = json.loads(run["errors_json"]) if run["errors_json"] else []
    if reasons:
        return f"{head}: " + "; ".join(_fmt(r) for r in reasons)
    if dropped > 0:
        # Counts show drops but no per-item reasons were stored — be honest.
        return f"{head} (per-item reasons not recorded — run predates T58)"
    return head


def _fmt(reason: dict) -> str:
    """One drop as a single line: ``[stage] reason (identifier)``.

    pyshacl reports are multi-line — collapse whitespace + cap length so one
    drop can't become a wall of wrapped text. The ``item`` (extract raw) or
    ``type`` (SHACL/insert class) tail distinguishes two same-reason drops.
    """
    text = " ".join(str(reason.get("reason", "")).split())
    if len(text) > 200:
        text = text[:197] + "..."
    tag = reason.get("item") or reason.get("type")
    base = f"[{reason.get('stage', '?')}] {text}"
    return f"{base} ({tag})" if tag else base


def _resolve_sha(paper: str) -> str:
    """A 64-hex string is a sha256; anything else is a path, hashed via T07."""
    s = paper.strip()
    if len(s) == 64 and all(c in string.hexdigits for c in s):
        return s.lower()
    from .read_paper import read_paper  # same hashing path as the cache key

    return read_paper(s)["sha256"]
