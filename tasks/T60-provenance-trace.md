# T60 — trace (provenance lookup in chat)

**Status:** planned · **Group:** custom agent · **Priority:** medium

## Why
"Where did this 236 mV come from?" The human-verify loop wants provenance answerable in chat, not only
in the viewer.

## Current situation
- Every measurement carries full provenance in the graph — the PROV activity node holds `page`,
  `bbox_*`, `sourceText`, `parserName`, `runId` (`store.py`).
- The FastAPI viewer renders it on hover (T31); `sparql_query` *can* fetch it but the agent must know
  the exact predicates.
- No canned, agent-friendly provenance lookup.

## What to build
A tool `trace(value_or_measurement)` that resolves a measurement and returns its source: paper (sha +
title/DOI), page, bbox, the verbatim `source_text`, parser, and run_id. A thin canned-SPARQL wrapper.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_trace.py -q
# seeded graph → trace returns page/bbox/source_text/parser/run_id for a known measurement
```

## Will touch
- `tools/` (new) wrapping `RDFStore.sparql`, `tools/__init__.py`, `tests/`
- Reuse: the `store.py` provenance predicates (read-only)

## Out of scope / notes
- Editing or removing triples (graph stays append-only by run_id).
- Disambiguating when several measurements share a value — return all matches.
