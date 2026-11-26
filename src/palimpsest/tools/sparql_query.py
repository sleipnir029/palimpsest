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
    out = json.dumps(rows, indent=2, default=str)
    notes = _prefix_notes(query)
    return ("\n".join(notes) + "\n" + out) if notes else out


def _prefix_notes(query: str) -> list[str]:
    """Flag a palimpsest prefix declared with the wrong IRI (e.g. https for PROV-O):
    such a query silently matches nothing, and the agent may retry it unchanged."""
    import re

    from palimpsest.store import _PREFIX

    notes = []
    for name, iri in re.findall(r"PREFIX\s+(\w+:)\s*<([^>]*)>", query, re.IGNORECASE):
        want = _PREFIX.get(name)
        if want and iri != want:
            notes.append(f"note: you declared PREFIX {name} <{iri}>, but the graph uses "
                         f"<{want}>; patterns with {name} will not match.")
    return notes
