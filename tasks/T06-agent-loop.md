# T06 — Agent loop with cache_control

## Why
The core of palimpsest. ~80 LOC implementing think → act → observe, modeled on Thorsten Ball's "How to Build an Agent" and Anthropic's cookbook patterns/agents. Everything else hangs off this.

## Input state
- T04 (AnthropicProvider) and T05 (CostMeter) merged.
- `src/palimpsest/agent.py` is an empty stub.
- `src/palimpsest/tools/__init__.py` exists (empty).

## Output state
- File `src/palimpsest/tools/__init__.py` exports a module-level `TOOLS: dict[str, callable]` (initially empty `{}`) and a `register(name, schema)` decorator that adds the function to TOOLS.
- File `src/palimpsest/agent.py` exports:
  - Class `MaxTurnsExceeded(Exception)`.
  - Class `Agent`:
    - `__init__(self, provider, cost_meter, tools: dict | None = None, system_prompt: str = "", max_turns: int = 40)`.
    - `def run(self, user_msg: str) -> str` — the loop:
      1. Append user message.
      2. For up to `max_turns`:
         - Call `cost_meter.check_or_raise(projected_eur=0.05)` (conservative).
         - Call `provider.complete(system=self.system_prompt, messages=self.messages, tools=list(self.tools.values()), cache_breakpoints=["system", "tools"])`.
         - Compute actual cost from `resp.usage` × Sonnet 4.5 pricing: input $3/M, output $15/M, cache_read $0.30/M, cache_create $3.75/M (5-min) or $6/M (1-hour; for MVP use 5-min). Convert USD → EUR at 0.92.
         - `cost_meter.record_llm("claude-sonnet-4-5", eur, detail=f"turn {turn}")`.
         - Append assistant message.
         - If no tool calls: return `resp.text`.
         - Otherwise dispatch each tool call (look up in TOOLS, validate input, run, append tool_result).
      3. Raise `MaxTurnsExceeded`.
  - The messages list lives on the Agent instance (`self.messages`), starts empty, includes user/assistant/tool roles.
- File `tests/test_agent.py` covers:
  - `test_no_tools()` — Agent with empty tools, asks "Reply with exactly 'pong'", returns "pong", cost ledger has 1 LLM entry.
  - `test_cache_hit_on_second_run()` — call `run()` twice on the same Agent; second response has `cache_read_input_tokens > 0`. System prompt must be ≥ 1024 tokens (pad it).
  - `test_max_turns()` — register a tool that always errors; agent stops at max_turns and raises.

## Verification
```bash
pixi run pytest tests/test_agent.py -v -s
```
Three tests passed. The cache test prints `cache_read = NNN` proving the cache is active.

## Will touch
- `src/palimpsest/agent.py` (full implementation)
- `src/palimpsest/tools/__init__.py` (TOOLS dict + register decorator)
- `tests/test_agent.py` (new)

## Will NOT touch
- Any individual tool file.
- Any provider file (T04 stays as is).
- `cost.py` (T05 stays as is).

## Out of scope
- Adding real tools → T07.
- Slash command interception → T27.
- Persistent message history across sessions → not in MVP.
- Compacting context → not in MVP.

## Notes / references
- Design ref: §F2 agent loop architecture.
- Anthropic cookbook: https://github.com/anthropics/anthropic-cookbook/tree/main/patterns/agents
- Thorsten Ball: https://ampcode.com/notes/how-to-build-an-agent
- Aim for 80–120 LOC in agent.py. If you write more, something is wrong.
- The TOOLS registry is a module-level dict, NOT a class attribute. Tools register themselves at import time.
