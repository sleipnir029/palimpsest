# T75 — Streaming + interruptible agent replies

## Why
The reply landed as a single blob after the whole turn (multi-second, sometimes
multi-minute) finished — the TUI felt dead. And Esc only cancelled at a turn
boundary, so a long in-flight generation ran to completion regardless.

## Input state
- T26 TUI, T63 live tool trace, T65 interrupt-turn (boundary-only cancel).
- `provider.complete()` was synchronous (`messages.create`, no streaming).

## Output state (delivered)
- `AnthropicProvider.complete(on_text=…)` streams via `messages.stream()`, pushing
  text deltas to `on_text`, then assembles the SAME `LLMResponse` (tool_use + usage)
  from `get_final_message()`. `on_text=None` (CLI/extraction) keeps the exact old path.
- The agent passes `on_text` only when a supervisor watches (`on_event` set); deltas
  render into one live `Markdown` widget, sealed once per turn (no double-render even
  when final text differs from the deltas by trailing whitespace).
- `StreamCancelled`: `Agent._stream_delta` raises it when `cancel_event` is set; the
  provider re-raises (never falls back to a fresh paid call); the loop returns a
  `[cancelled]` note, leaving the partial reply on screen. Esc now stops *now*.
- Known debt: the abandoned call's partial tokens go unbilled — a small, bounded
  under-count gated by the pre-call `check_or_raise(0.05)`, so the €50 cap still holds.

## Verification
`pixi run pytest tests/test_anthropic.py tests/test_tui.py tests/test_agent.py -q -m "not live"`
- `test_streaming_emits_deltas_and_assembles_same_shape`
- `test_streaming_cancel_propagates_without_fallback`
- `test_streamed_reply_renders_once_via_deltas`, `test_streaming_cancel_returns_cancelled_note`
- Manual (needs a key): confirm DeepSeek's endpoint streams; else it degrades to the
  blocking fallback (Sonnet is the guaranteed-streaming provider).

## Will touch
- `src/palimpsest/providers/anthropic.py`, `src/palimpsest/agent.py`, `src/palimpsest/tui/app.py`

## Will NOT touch
- The extraction path (`tools/extract.py`) — stays non-streaming, byte-for-byte.
- The €-budget gate logic (only the cancel under-count is documented, not changed).
