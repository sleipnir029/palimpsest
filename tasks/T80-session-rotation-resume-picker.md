# T80 — Session rotation + /resume picker

## Why
There was one rolling `session.jsonl` shared across all launches — so `/resume`
couldn't list sessions to pick from, and up-arrow history had no cross-session
source. Users expect distinct, selectable past conversations (Claude Code style).

## Input state
- T66 single append-only `.palimpsest/session.jsonl`.
- `/resume` blindly reloaded that one file.

## Output state (delivered)
- Sessions rotate per launch: `.palimpsest/session-<ts>-<uuid>.jsonl`. `SessionLog.load()`
  keeps its singleton-ish meaning (own file if written, else newest on disk).
- New module helpers: `session_paths` (newest-first by mtime), `load_session`,
  `prior_sessions(exclude=current)`, `session_recap`, `recent_inputs(max_sessions=5)`.
- `/resume [n]` lists prior sessions via autocomplete (numbered, with a one-line
  recap), excludes the in-progress session, bounds-checks, and falls back to the
  agent's own loader when there are no rotated priors.
- Up-arrow history (T76) seeds from `recent_inputs()` across the last 5 sessions.
- Invariants preserved: gitignored (`.palimpsest/` under `workspace/`), secret
  redaction unchanged (it lives in `agent._redact_secrets`, not `session.py`).

## Verification
`pixi run pytest tests/test_session.py tests/test_slash_budget_cost.py -q -m "not live"`
- `test_session_paths_newest_first`, `test_recent_inputs_spans_sessions_oldest_first`,
  `test_prior_sessions_excludes_current`, `test_resume_picks_specific_prior_session`,
  `test_transcript_is_gitignored` (updated for the rotated filename)

## Will touch
- `src/palimpsest/session.py`, `src/palimpsest/tui/slash.py` (`_resume`, autocomplete),
  `src/palimpsest/tui/app.py` (history seed)

## Will NOT touch
- `/undo` (git-based; the transcript is gitignored either way).
