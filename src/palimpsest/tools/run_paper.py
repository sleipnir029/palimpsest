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
    from palimpsest.store import RDFStore

    summary = run_paper(
        pdf_path,
        parser_name,
        skill_name,
        store=RDFStore("store"),          # on-disk graph the viewer reads
        cost_meter=CostMeter("palimpsest.db"),  # shared €50 ledger
    )
    return json.dumps(summary, indent=2)
