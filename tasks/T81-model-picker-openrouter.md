# T81 — Two-level model picker + priced models + OpenRouter extraction

## Why
`/use <role> <name>` offered one default model per provider, no granularity, and
OpenRouter wasn't usable at runtime. Users want to pick a provider, then a
specific model — without ever under-counting the €50 cap.

## Input state
- Flat `/use orchestration|extraction <name>`; providers = deepseek/sonnet/anthropic/gemini.
- CLAUDE.md barred LLM gateways from the whole runtime.

## Output state (delivered)
- **Priced model factories** (`providers/__init__.py`): `_haiku` (claude-haiku-4-5,
  $1/$5, 0.1×/1.25× cache) and `_deepseek_pro` (deepseek-v4-pro, $0.435/$0.87) — each
  carries its own INSTANCE price table so `agent._cost_eur` meters it correctly.
  Prices reused from the verified `experiments/llm_matrix.py` specs (not fabricated).
- **Two-level `/use <role> <provider> [model]`**: `_PROVIDER_MODELS` registry →
  autocomplete shows providers, then that provider's models with comments (names +
  comments, no prices, no network — per user choice). Orchestration lists only
  loop-capable providers (deepseek, anthropic); extraction lists all four. z.ai is
  reachable as a curated OpenRouter slug (`z-ai/glm-4.6`).
- **OpenRouter extraction carve-out** (CLAUDE.md updated, user-authorized 2026-06-22):
  `/use extraction openrouter <slug>`, model via `OPENROUTER_MODEL`. Budget-safe —
  set `OPENROUTER_PRICE_IN/OUT` for accuracy, else conservative Sonnet fallback. Gateway
  is barred from orchestration only.
- `/config` gains `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, and the
  RunPod per-parser template ids; `config._PROVIDER_KEY` maps the new providers.

## Verification
`pixi run pytest tests/test_slash_budget_cost.py tests/test_tui.py -q -m "not live"`
- `test_use_orchestration_specific_model_switches`, `test_deepseek_pro_carries_its_own_pricing`
- `test_openrouter_is_extraction_only`, `test_use_extraction_gateway_model_sets_env`
- `test_menu_for_argument_values` (two-level provider→model autocomplete)

## Will touch
- `src/palimpsest/providers/__init__.py`, `src/palimpsest/tui/slash.py`,
  `src/palimpsest/config.py`, `CLAUDE.md`

## Will NOT touch
- The agent-loop Anthropic-wire lock (gateways never drive orchestration).
- opus-4.8 — excluded (no verified price table; would under-count the cap).
