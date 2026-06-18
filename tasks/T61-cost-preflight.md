# T61 — cost pre-flight estimate

**Status:** planned · **Group:** custom agent · **Priority:** low

## Why
Before extracting, tell the user the likely spend (uncached parses = GPU €; extraction = LLM €) so they
approve knowingly — the supervised-spend complement to the hard cap.

## Current situation
- `CostMeter` records *actual* spend and enforces the cap; there is no pre-flight estimate.
- `parse_with_cache` already short-circuits cached papers (free), so the estimate hinges on how many
  papers are uncached.

## What to build
A read-only tool `estimate_cost(papers, parser)` that counts uncached parses × a rough GPU €/paper +
extractions × a rough LLM €/paper and returns a range (e.g. "~€0.2–0.4: 2 uncached parses + 3
extractions"). Rough by design.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_estimate_cost.py -q
# mixed cached/uncached set → estimate scales with the uncached count
```

## Will touch
- `tools/` (new), `tools/__init__.py`, `tests/`
- Reuse: `cache` (what's cached), the per-paper cost figures recorded in DEVIATIONS/`cost_ledger`

## Out of scope / notes
- Exact pricing — a rough, clearly-labeled estimate is enough to inform a go/no-go.
