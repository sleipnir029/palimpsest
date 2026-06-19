# T62 — graph_summary / describe_schema

**Status:** planned · **Group:** constrained-autonomy (thesis core) · **Priority:** high

> **Re-prioritised 2026-06-19** (was: custom agent / low / "convenience"). This is the
> **read side** of the run-time-autonomy spine the supervisor meeting demanded: for the
> agent to "use the ontology to build the graph" *without Claude Code present*, it must
> be able to **read the schema** (classes, slots, units, IRIs) at run time. Today the
> schema reaches the model only as a JSON blob silently embedded in the extraction
> prompt — the agent *loop* never sees it. `describe_schema` is also what the T69
> consistency gate checks against. Pairs with T69 (gate) + T70 (self-diagnosis).
> See `report/supervisor-answers-2026-06-19.md` §2 (mechanism #2) and the plan.

## Why
So the agent can answer "what's in the graph?" and build correct SPARQL without re-reading the raw
LinkML YAML each time — and, more importantly, so it can read the schema contract
(classes/slots/units/IRIs) at run time instead of relying on a prompt-embedded blob it
cannot introspect.

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
- `graph_summary` (counts over the live graph) is the lower-value half; **`describe_schema`
  is the autonomy-critical half** — if scoping down, build `describe_schema` first.
- Consistency-*checking* a skill against this schema is T69, not here. T62 only exposes
  the schema for reading; T69 enforces the skill↔schema match.
