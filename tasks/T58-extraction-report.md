# T58 — extraction_report (surface drops + reasons)

**Status:** planned · **Group:** custom agent · **Priority:** high

## Why
`extract()` silently drops measurements that fail validation — the human and the agent never learn
*why* something is missing. This is the #1 trust gap: you can't verify what you can't see.

## Current situation
- `extract()` returns `(valid, errors)` where `errors` is `list[(Exception, raw_item)]` — the drop
  reasons (mis-citation digit guard, unit mismatch, missing evidence, unknown class, Pydantic) are
  already computed.
- `pipeline.run_paper` additionally logs SHACL drops + insert refusals via `log.warning`.
- None of this reaches the agent or the TUI; it goes to a log file.

## What to build
Expose the drops with reasons. Either a tool `extraction_report(pdf, parser)` that returns the last
run's (or a fresh dry-run's) dropped items + human-readable reasons, or have `run_paper` return/persist
the `errors` and a tool to read them. Output: "extracted N, dropped M: [value 236 not in cited span;
unit V≠mV; …]".

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_extraction_report.py -q
# stub extract returning known errors → report lists each dropped item with its reason
```

## Will touch
- `tools/` (new), possibly `pipeline.run_paper` (return/persist `errors`), `tests/`
- Reuse: the `(valid, errors)` tuple `extract()` already produces

## Out of scope / notes
- Auto-correcting drops or two-pass re-extraction — the agent re-runs; correction is a later concern.
- Pairs with **T57** (which shows the dropped *count*; this gives the *reasons*).
