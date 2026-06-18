# T63 — Live tool-call trace in the TUI

**Status:** planned · **Group:** general agent · **Priority:** high

## Why
The human supervises — but the TUI shows only "…thinking" then the final reply. Every tool call
(`extract_paper`, `write_file`, `bash`) happens invisibly inside `agent.run()`. You can't supervise
what you can't see. This is the highest-leverage general feature and costs €0.

## Current situation
- `tui/app.py` runs `agent.run()` in a `@work(thread=True)` worker and writes only the final reply to
  the `RichLog`.
- `Agent._dispatch` produces every tool call + result but emits them nowhere observable.

## What to build
A passive observer hook on the agent — e.g. an optional `on_event(event)` callback (or a thread-safe
queue) that fires per tool call and per result — and TUI rendering that streams them live:
`→ extract_paper(papers/x.pdf)` … `← 14 measurements, 2 dropped`. Truncate long results.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_tui.py -q
# pilot: a stub agent that calls a tool → the log shows the tool-call line BEFORE the final reply
```

## Will touch
- `agent.py` (emit events from `_dispatch`/`run`), `tui/app.py` (render via `call_from_thread`)
- `tests/test_tui.py`

## Out of scope / notes
- Token-level streaming of the LLM's text reply (separate, provider-side).
- Strictly a passive observer — **no behavior change** to the agent loop.
