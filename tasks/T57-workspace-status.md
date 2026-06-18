# T57 — workspace_status (orientation)

**Status:** planned · **Group:** custom agent · **Priority:** high

## Why
When the agent is spawned in a folder (or a new session starts), it has no single answer to "what's
here and what have I done?" — the session-opener, and the basis for the "agent decides the next task
or asks the user" behavior.

## Current situation
- `cache.list_all_papers()` (added T34) lists papers known to the parse cache.
- `RDFStore.sparql()` can count what's in the graph, but the caller must know the predicates.
- `papers/` holds the PDFs; `read_paper` hashes them.
- `extract()` returns `(valid, errors)` but the counts are never surfaced.
- Nothing combines these into one view.

## What to build
A read-only tool `workspace_status()` that reports, for the workspace: PDFs present; which are parsed
(per-parser cache hit); which are extracted (in the graph) with a measurement count; a per-paper
**dropped-count teaser** (full reasons → T58); and what's pending. Returns a compact summary
(string or JSON). €0 — pure read.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_workspace_status.py -q
# synthetic cache + seeded graph → summary lists papers/parsed/extracted/pending correctly
```

## Will touch
- `tools/workspace_status.py` (new), `tools/__init__.py` (register), `tests/test_workspace_status.py`
- Reuse: `cache.list_all_papers`, `RDFStore.sparql`, `read_paper`

## Out of scope / notes
- The detailed per-measurement drop report → **T58**.
- Keep it deterministic and read-only; it is the natural target for a future `/status` slash command.
