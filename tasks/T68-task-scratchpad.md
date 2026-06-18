# T68 — Task scratchpad (todo list)

**Status:** planned · **Group:** general agent · **Priority:** low

## Why
For multi-step jobs ("extract these 5 papers → summarize → plot"), the agent can lose the thread. A
maintained checklist keeps it on track and shows the user progress.

## Current situation
- No task tracking; the agent relies entirely on conversation memory, which degrades over a long job.

## What to build
A lightweight todo the **same** agent maintains via a tool (add / update / complete items), rendered to
the user. State persists across turns within a session.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_scratchpad.py -q
# agent adds + completes items via the tool; state survives across turns
```

## Will touch
- `tools/` (new todo tool), `tools/__init__.py`, optional TUI render, `tests/`

## Out of scope / notes
- **Critical boundary:** this is a passive memory aid driven by the one agent — NOT a separate
  planner/critic/router agent (which CLAUDE.md bans on sight). The LLM updates the list; no second
  agent decides anything. Keep it firmly on that side of the line.
- No auto-decomposition of tasks.
