# T04 — AnthropicProvider class

## Why
Need a single, focused wrapper around the Anthropic SDK that the agent loop can call. This is the only LLM client used in the MVP; fallback providers (Haiku, DeepSeek, Gemini) come later as subclasses with the same interface.

## Input state
- T02 merged. `src/palimpsest/providers/__init__.py` exists (empty).
- `pixi run python -c "import anthropic; print(anthropic.__version__)"` succeeds.
- `.env` contains `ANTHROPIC_API_KEY=sk-ant-...`.

## Output state
- File `src/palimpsest/providers/anthropic.py` exists and exports:
  - A dataclass `LLMResponse` with fields: `text: str`, `tool_calls: list[dict]`, `usage: dict`, `raw: dict`.
  - A class `AnthropicProvider` with:
    - `__init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-5")` — reads `ANTHROPIC_API_KEY` from env if `api_key` is None.
    - `name: str` class attribute = `"claude-sonnet-4-5"`.
    - `def complete(self, system: str, messages: list[dict], tools: list[dict] | None = None, cache_breakpoints: list[str] | None = None) -> LLMResponse:` — calls `anthropic.Anthropic().messages.create(...)`. Sets `max_tokens=4096`. If `cache_breakpoints` includes `"system"`, adds `cache_control={"type": "ephemeral"}` to the system message. If it includes `"tools"`, adds the same to the last tool. Returns `LLMResponse` with `usage = {"input_tokens": ..., "output_tokens": ..., "cache_read_input_tokens": ..., "cache_creation_input_tokens": ...}`.
- File `src/palimpsest/providers/__init__.py` exports `AnthropicProvider`, `LLMResponse`.
- File `tests/test_anthropic.py` exists with two tests:
  - `test_smoke()` — instantiates provider, calls `complete(system="You are helpful.", messages=[{"role": "user", "content": "Reply with exactly: ok"}])`. Asserts response.text strips to `"ok"`. **This test calls the real API and costs ~$0.001.**
  - `test_cache_control()` — calls `complete` twice with `cache_breakpoints=["system"]`, asserts second response has `usage["cache_read_input_tokens"] > 0`. Requires system prompt of at least 1024 tokens (use a padding string of repeated text).

## Verification
```bash
pixi run pytest tests/test_anthropic.py -v -s
```
Must show 2 passed. Output of `test_cache_control` must include a printed `cache_read_input_tokens` > 0.

## Will touch
- `src/palimpsest/providers/anthropic.py` (new)
- `src/palimpsest/providers/__init__.py` (edit: add exports)
- `tests/test_anthropic.py` (new)

## Will NOT touch
- Any other provider file (Haiku, DeepSeek, Gemini come later).
- `src/palimpsest/agent.py`, `src/palimpsest/cost.py`, or any other module.
- `pixi.toml`, `pyproject.toml`.

## Out of scope
- Haiku/DeepSeek/Gemini providers → later tasks (we have NOT scheduled these for MVP; the design allows them but they only get built if the user explicitly asks).
- Cost tracking (the test will spend money but does NOT log it — that's T05).
- Streaming responses.
- Retries on rate limits.

## Notes / references
- Anthropic SDK docs: https://docs.claude.com/en/api/messages
- Prompt caching docs: https://docs.claude.com/en/docs/build-with-claude/prompt-caching — note cache_control is a per-block field, not a top-level kwarg.
- Model id: `claude-sonnet-4-5` (NOT `claude-3-5-sonnet-...` — that's the old naming).
- Pricing: $3/M input, $15/M output, cache read $0.30/M. Tests cost cents.
- Do NOT install or import `langchain-anthropic`. Direct SDK only.
- If `anthropic.Anthropic()` complains about missing key, the test should `pytest.skip(...)` with a clear message — do not hardcode a key.
