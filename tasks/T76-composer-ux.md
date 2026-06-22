# T76 — Composer UX: multi-line input, history, Esc-focus fix

## Why
The input was a single-line `Input`: no multi-line composing, no recall of past
prompts, and (after the TextArea swap) Esc stole focus and froze the app.

## Input state
- T26 single-line `Input` composer with slash autocomplete.

## Output state (delivered)
- `PromptArea(TextArea)` composer: Enter submits, Ctrl+J inserts a newline; CSS
  `height: auto; max-height: 12` grows with content then scrolls internally.
- **Esc-focus fix:** TextArea's built-in Escape calls `screen.focus_next()` (froze the
  app). `PromptArea._on_key` intercepts Escape → routes to `action_cancel_turn`, keeps
  focus.
- **Input history:** up/down recall prior prompts, but only at the composer's top/bottom
  edge (else they move the cursor between lines). Seeded across launches from
  `session.recent_inputs()`. Slash commands are kept in history; while *browsing* a
  recalled line the autocomplete menu is suppressed so it can't hijack up/down.
- Autocomplete (`_sync_menu`, `action_menu_complete`) rewired to TextArea's `.text` /
  `cursor_location` API.

## Verification
`pixi run pytest tests/test_tui.py -q`
- `test_ctrl_j_inserts_newline_without_submitting`
- `test_up_arrow_recalls_input_history`, `test_history_navigates_up_up_down`
- `test_recalled_slash_command_does_not_open_menu`
- `test_escape_requests_cancellation_when_in_flight` (still green post-swap)
- Manual: confirm the auto-grow feel (headless tests can't see widget growth).

## Will touch
- `src/palimpsest/tui/app.py` (`PromptArea`, history, on_mount seed), `src/palimpsest/tui/styles.tcss`

## Will NOT touch
- The slash dispatcher semantics (only the widget the autocomplete reads from changed).
