# T65 — Interrupt / cancel a turn

**Status:** done · **Group:** general agent · **Priority:** medium

## Why
Stop a wrong-direction or runaway turn (one heading toward `max_turns`) without killing the app.

## Current situation
- The TUI disables input during the `@work` worker; a Textual thread worker can't be cleanly cancelled
  (noted in T26/DEVIATIONS) and there is no stop key.
- `Agent.run` loops up to `max_turns` (40) with no cancellation check between turns.

## What to build
A cancellation flag the agent checks at each turn boundary (a `threading.Event` passed in or set on the
agent), bound to a TUI key (e.g. Esc). When set, `Agent.run` returns early with a "cancelled" note and
the input re-enables.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_agent.py -q
# stub provider loops; set the cancel event mid-run → run() exits early, no MaxTurnsExceeded
```

## Will touch
- `agent.py` (check a cancel event in the loop), `tui/app.py` (key → set event, re-enable input)
- `tests/test_agent.py`

## Out of scope / notes
- Interrupting an in-flight provider HTTP call (hard) — cancellation takes effect at the **next turn
  boundary**, which is enough to stop a multi-turn runaway.
