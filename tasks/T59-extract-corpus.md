# T59 — extract_corpus (batch, idempotent)

**Status:** planned · **Group:** custom agent · **Priority:** medium

## Why
`extract_paper` is one-at-a-time. The spawn-and-go workflow wants a single instruction: "extract
every paper in `papers/` that isn't in the graph yet."

## Current situation
- `extract_paper` (T53) wraps `pipeline.run_paper` for one PDF.
- `cache.list_all_papers()` lists known papers; a SPARQL count can tell which are already extracted.
- No loop / idempotent skip exists.

## What to build
A tool `extract_corpus(parser, skill)` that iterates the PDFs in `papers/`, skips any already in the
graph, runs the pipeline on the rest, and returns a per-paper summary. Metered; **stops cleanly at the
budget cap** (CostMeter `check_or_raise`) rather than erroring mid-corpus.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_extract_corpus.py -q
# 2 papers, 1 already in graph → only the new one is processed; summary reports skip + done
```

## Will touch
- `tools/` (new) looping `pipeline.run_paper`, `tools/__init__.py`, `tests/`
- Reuse: `cache.list_all_papers`, `CostMeter`, `RDFStore.sparql` (to detect already-extracted)

## Out of scope / notes
- Parallel parsing and corpus-wide parser comparison (thesis, deferred).
- Honor the budget: log + stop at the cap, don't half-process and crash.
