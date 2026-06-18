# T67 — Context compaction

**Status:** planned · **Group:** general agent · **Priority:** medium

## Why
`self.messages` grows unbounded within a session; a long session eventually overflows the model's
context window.

## Current situation
- Messages accumulate across `run()` calls with no trimming or summarization.
- `max_turns=40` caps a single `run()` call but NOT the cross-call session history.

## What to build
When the history exceeds a token threshold, summarize the older turns into a compact note and keep the
recent turns verbatim, then continue. One extra metered LLM call only when triggered.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_agent.py -q
# feed a long history past the threshold → it compacts below it while preserving recent turns
```

## Will touch
- `agent.py` (a compaction step before the provider call), `tests/test_agent.py`

## Out of scope / notes
- Provider-side context management; vector retrieval (**banned** by CLAUDE.md).
- Keep it predictable: trigger on a token threshold, summarize deterministically, charge the one call
  to the meter like any other.
