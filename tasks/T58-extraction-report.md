# T58 — extraction_report (surface drops + reasons)

**Status:** done (2026-06-18) · **Group:** custom agent · **Priority:** high

## Why
`extract()` silently drops measurements that fail validation — the human and the agent never learn
*why* something is missing. This is the #1 trust gap: you can't verify what you can't see.

## Current situation
- `extract()` returns `(valid, errors)` where `errors` is `list[(Exception, raw_item)]` — the drop
  reasons (mis-citation digit guard, unit mismatch, missing evidence, unknown class, Pydantic) are
  already computed.
- `pipeline.run_paper` additionally logs SHACL drops + insert refusals via `log.warning`.
- None of the *reasons* reaches the agent or the TUI; it goes to a log file.
- **T57 already built the persistence + count layer** you would otherwise have to add here:
  `src/palimpsest/runs.py` (`ExtractionRunLog`, the `extraction_runs` table in `palimpsest.db`) and a
  `run_log.record(...)` call at the end of `pipeline.run_paper` that stores `n_errors`/`n_extracted`/
  `n_validated`/`n_inserted` per run. So the *count* of drops is already persisted and surfaced
  (`workspace_status` shows "N found · M inserted · K dropped"). **What's still missing is the
  per-item reasons** — `extract()`'s `errors` list (and run_paper's SHACL/insert drop reasons) are
  still discarded after the counts are taken.

## What to build
Expose the drops **with reasons** — the count is done (T57), this adds the *why*. Recommended path now
that the run log exists: persist the per-item reasons alongside the counts (e.g. an `errors_json` /
drop-reasons column or a sibling `extraction_drops` table keyed by `(paper_sha256, run_id)`), written
from `run_paper` where `extract()`'s `errors` + the SHACL/insert drops are already in scope; then a tool
`extraction_report(pdf|sha, parser)` reads the latest run's dropped items + human-readable reasons.
Reuse `ExtractionRunLog` (extend it) rather than adding a parallel store. Output: "extracted N, dropped
M: [value 236 not in cited span; unit V≠mV; …]". (T57 deliberately stopped at counts and left this seam;
`workspace_status` already points the user to `extraction_report (T58)`.)

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_extraction_report.py -q
# stub extract returning known errors → report lists each dropped item with its reason
```

## Will touch
- `tools/extraction_report.py` (new), `src/palimpsest/runs.py` (extend `ExtractionRunLog` to store/read reasons), `pipeline.run_paper` (persist the reasons it already logs), `tests/`
- Reuse: the `(valid, errors)` tuple `extract()` already produces; `ExtractionRunLog` + the `extraction_runs` table (T57) — extend, don't duplicate

## Out of scope / notes
- Auto-correcting drops or two-pass re-extraction — the agent re-runs; correction is a later concern.
- Pairs with **T57** (which shows the dropped *count*; this gives the *reasons*).
