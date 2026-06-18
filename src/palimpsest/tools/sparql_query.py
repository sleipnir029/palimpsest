"""`sparql_query` tool — query the RDF knowledge graph conversationally.

Wraps ``RDFStore.sparql`` (T24) over the on-disk ``store/`` the viewer reads, so
the agent can answer cross-paper questions ("all overpotentials by catalyst")
without the user dropping to a query console. Read-only; costs nothing.

This is the agent-facing half of T40 — the bespoke ``run_queries.py`` runner is
subsumed here; keep the 5 ``queries/*.rq`` files as reproducible thesis artifacts
the agent can read with ``read_file`` and run through this tool.
"""

from __future__ import annotations

import json

from . import register


@register("sparql_query", {
    "description": "Run a SPARQL SELECT over the RDF graph and return the rows as JSON. Use for cross-paper analysis of extracted measurements.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "A SPARQL SELECT query."}},
        "required": ["query"],
    },
})
def sparql_query(query: str) -> str:
    # Lazy import: store.py pulls in pyoxigraph + the generated schema; defer that
    # cost out of the `tools/__init__` scan until the agent actually queries.
    from palimpsest.store import RDFStore

    rows = RDFStore("store").sparql(query)
    return json.dumps(rows, indent=2, default=str)
