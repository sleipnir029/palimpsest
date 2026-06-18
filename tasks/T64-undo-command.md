# T64 — /undo (revert the last turn)

**Status:** done · **Group:** general agent · **Priority:** high

## Why
"No, undo that." Leverage the dulwich layer (T55) for one-command rollback of the last turn's file
changes — the natural pair to live tool visibility (T63).

## Current situation
- T55 commits per mutating action and tags each turn (`turn-<session>-<n>`).
- No command exposes a revert; the human must drop to `git` manually.

## What to build
A `/undo` slash command (+ a `versioning` helper) that restores the workspace to the previous turn tag
(or to the commit before the last turn's commits) via dulwich, and reports what was undone. Records the
revert as a new commit (history stays append-only and auditable).

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_versioning.py -q
# make changes across a turn → /undo → files restored to the prior turn, a revert commit recorded
```

## Will touch
- `tui/slash.py` (`/undo` handler), `versioning.py` (revert/reset-to-tag helper), `tests/`
- Reuse: the per-turn tags from `tag_turn`

## Out of scope / notes
- Undoing *graph* inserts (the graph is append-only by run_id) — a separate concern.
- Start with single-step (last turn) undo; a multi-step undo stack can come later.
