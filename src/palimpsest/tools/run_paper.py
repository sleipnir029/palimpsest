"""`extract_paper` tool — run one PDF end-to-end into the graph.

Exposes the T25 ``run_paper`` pipeline (parse via cache → extract → SHACL →
provenance insert) to the agent, so "extract this paper" is a single tool call
rather than a CLI invocation the human runs. Persists to the on-disk ``store/``
the viewer reads, and meters spend against the shared €50 ledger.

Imports are deferred to call time: ``pipeline`` pulls in ``tools.extract`` (and
the parser/store stack), which would form an import cycle if loaded while
``tools/__init__`` is still running — the same convention ``__main__.py`` uses.

Note: ``store/`` is single-writer RocksDB — run with the viewer stopped, or the
store open will fail (surfaced to the agent as a tool error).
"""

from __future__ import annotations

import json

from . import register


@register("extract_paper", {
    "description": (
        "Parse a PDF (cached parser output if available, else a GPU parse), extract "
        "measurements with the LLM, SHACL-validate, and insert into the RDF graph "
        "with provenance. Returns a summary of how many measurements were extracted, "
        "validated, and inserted."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pdf_path": {"type": "string"},
            "parser_name": {"type": "string", "description": "docling|mineru|dots|paddle (default mineru)."},
            "skill_name": {"type": "string", "description": "Extraction skill (default oer-extraction)."},
        },
        "required": ["pdf_path"],
    },
})
def extract_paper(pdf_path: str, parser_name: str = "mineru", skill_name: str = "oer-extraction") -> str:
    from palimpsest.cost import CostMeter
    from palimpsest.pipeline import run_paper
    from palimpsest.runs import ExtractionRunLog
    from palimpsest.store import RDFStore

    try:
        summary = run_paper(
            pdf_path,
            parser_name,
            skill_name,
            store=RDFStore("store"),          # on-disk graph the viewer reads
            cost_meter=CostMeter("palimpsest.db"),  # shared €50 ledger
        )
    except KeyError as exc:
        # A fresh (uncached) parse spins a RunPod pod, which reads RUNPOD_API_KEY
        # (gpu_provider.py) and raises KeyError('RUNPOD_API_KEY') if unset. Match
        # only that — turn it into an actionable ask — and re-raise any other
        # KeyError so a genuine bug isn't mislabeled as missing config.
        if "RUNPOD_API_KEY" in str(exc):
            return ("missing config: RUNPOD_API_KEY — a fresh parse needs RunPod. "
                    "Ask the user to set it via /config set RUNPOD_API_KEY <key>.")
        raise

    # The summary's funnel (n_extracted → validated → inserted) hides the biggest
    # drop bucket: extract-level errors (n_errors) aren't in it. Read the run row
    # run_paper just recorded to get the true dropped count, and if anything
    # dropped, nudge the agent to diagnose the pattern (T70) and decide. Read-only,
    # €0 — never re-extracts on its own.
    dropped = 0
    run = ExtractionRunLog().latest_run(summary["paper_sha"], parser_name)
    if run is not None:
        dropped = run["n_errors"] + run["n_extracted"] - run["n_inserted"]
    return json.dumps(summary, indent=2) + _drop_nudge(dropped, pdf_path, parser_name)


def _drop_nudge(dropped: int, pdf_path: str, parser_name: str) -> str:
    """In-loop nudge: a drop-heavy run should prompt the agent to diagnose, not
    move on. Empty string when nothing dropped (no noise on a clean run)."""
    if dropped <= 0:
        return ""
    return (
        f"\n\n{dropped} measurement(s) dropped. Call "
        f"diagnose_run('{pdf_path}', '{parser_name}') to see whether the drops "
        f"are a systematic pattern (fix the skill/units and re-extract) or noise "
        f"(accept), then decide."
    )
