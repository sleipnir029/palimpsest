# T57 — workspace_status (orientation)

**Status:** ✓ done (2026-06-18) · **Group:** custom agent · **Priority:** high

> **Scope expansion (authorized).** The card said "€0 pure read" reusing only
> `cache.list_all_papers` / `RDFStore.sparql` / `read_paper`, touching only the new
> tool + `tools/__init__.py` + the test. But a *true* dropped count is not derivable
> read-only — drops (`extract()` errors + SHACL/insert drops) were computed at run
> time and discarded (`pipeline.py` threw away `_errors`; no runs table existed). Per
> user direction ("find the actual solve, industry best practice; don't fabricate a
> proxy or re-run the LLM"), T57 also added a persisted run log: `src/palimpsest/runs.py`
> (`ExtractionRunLog`, an `extraction_runs` table in `palimpsest.db` mirroring
> `parser_runs`) and one recording call in `pipeline.run_paper` (return dict unchanged).
> `workspace_status` reads it for a real dropped count. Weakens no code-enforced
> invariant (workspace confinement / provenance-on-insert / €-budget gate). See
> DEVIATIONS.md 2026-06-18. This is also the persistence layer **T58** now reads.

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
- Reuse: `cache.list_all_papers` (+ direct `cache.conn` reads for filename/page/parsers, à la `/cost`), `RDFStore.sparql`, `read_paper`
- **Added by the scope expansion (above):** `src/palimpsest/runs.py` (new) + `tests/test_runs.py` (new); `pipeline.py` (record a run); `tests/test_pipeline.py` (inject tmp run_log + recording test)

## Out of scope / notes
- The detailed per-measurement drop report → **T58**.
- Keep it deterministic and read-only; it is the natural target for a future `/status` slash command.
