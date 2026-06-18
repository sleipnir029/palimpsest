# T66 — Session transcript / persistence

**Status:** planned · **Group:** general agent · **Priority:** medium

## Why
The agent forgets everything between spawns (`self.messages` is per-process). A persistent transcript
lets you resume context and doubles as the **thesis reflection record** for free.

## Current situation
- `Agent.messages` lives in memory on the instance; nothing persists across `run()` calls beyond the
  process, and nothing at all across spawns.
- T55 versioning commits *files* but not the conversation.

## What to build
Append each turn (user message, tool calls + results, final reply) to a git-tracked session log in the
workspace (e.g. `.palimpsest/session.jsonl`). Optionally reload the recent tail into `messages` on spawn
so a new session resumes with context.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_session.py -q
# two turns → the log holds both; (optional) a fresh agent reloads the recent context
```

## Will touch
- `agent.py` (append per turn) + a small `session` helper; `tests/`
- Reuse: `policy.workspace_root`, the versioning `.gitignore`/commit path

## Out of scope / notes
- Full pi-style multi-session branching — just an append log + optional reload.
- Don't log secrets; the transcript is content + tool I/O, not env values.
