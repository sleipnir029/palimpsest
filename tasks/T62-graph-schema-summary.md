# T62 — graph_summary / describe_schema

**Status:** planned · **Group:** custom agent · **Priority:** low

## Why
So the agent can answer "what's in the graph?" and build correct SPARQL without re-reading the raw
LinkML YAML each time.

## Current situation
- `sparql_query` can compute summaries, but the agent must already know the schema.
- `read_skill` gives domain *prose*, not the structural list of measurement classes/slots.
- The generated schema (`schema/generated/`) has the structure but isn't agent-surfaced.

## What to build
One or both canned helpers: `graph_summary()` (counts by measurement type, #papers, #catalysts,
coverage) and `describe_schema()` (the measurement classes + their slots + units). Read-only.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_graph_summary.py -q
# seeded graph → summary returns per-type counts; describe_schema lists the 9 measurement classes
```

## Will touch
- `tools/` (new), `tools/__init__.py`, `tests/`
- Reuse: `RDFStore.sparql`, the generated `_CLASS_MAP`/schema, `normalize.UNIVERSAL_UNITS`

## Out of scope / notes
- Low priority — `sparql_query` covers the need today; this is convenience/ergonomics.
