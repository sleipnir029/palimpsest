# T77 — Conversation control: /clear, /export, context indicator

## Why
`agent.messages` grew unbounded (context rot + budget burn) with no reset; there
was no way to save a conversation; and nothing showed how much context the agent
was carrying.

## Input state
- T27 slash commands; Ctrl+L cleared only the display, not `agent.messages`.
- `Agent.last_usage` recorded per turn but unsurfaced.

## Output state (delivered)
- `/clear` resets `agent.messages = []` + `last_usage = {}` and wipes the display —
  a real context reset (Ctrl+L stays display-only).
- `/export` dumps the conversation to `workspace/transcript-<ts>.md` (markdown), routed
  through `policy.assert_writable` (same fence as `write_file`).
- Status bar appends `ctx ~Nk` from `agent.last_usage["input_tokens"]` — the live
  prompt size, no tokenizer dependency.

## Verification
`pixi run pytest tests/test_tui_integration.py tests/test_slash.py -q`
- `test_clear_and_export_integrate` (clears context; writes a transcript file)
- footer assertions include the `ctx` segment via `_status_text`

## Will touch
- `src/palimpsest/tui/slash.py` (`_clear`, `_export`, `_transcript_md`), `src/palimpsest/tui/app.py` (`_status_text`)

## Will NOT touch
- The session transcript on disk (T66) — `/clear` is in-memory only; the durable
  `.palimpsest/session-*.jsonl` record is untouched.
