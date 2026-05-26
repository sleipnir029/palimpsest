# T28 — /budget, /cost, /model slash commands

## Why
The three operational commands you'll use daily.

## Input state
- T27 merged.

## Output state
- `SLASH_COMMANDS` (in slash.py) extended with three handlers:
  - `/budget N` — parses N as int. Calls `cost_meter.set_budget(N)`. Returns status (e.g. `"budget cap → €75 (spent €12.40, headroom €62.60)"`). If N < spent, returns a refusal message.
  - `/cost` — returns multi-line summary: total spent, breakdown by LLM vs GPU, last 10 ledger entries.
  - `/model X` — switches active provider. X in {"sonnet","haiku","deepseek","gemini"}. Updates `app.agent.provider`. Notes that prompt cache will be invalidated for this session.
- Provider switching infrastructure:
  - For MVP, only `sonnet` (already implemented in T04) is wired. `/model haiku|deepseek|gemini` returns `"provider X not implemented yet; only 'sonnet' is available in MVP"`.
  - When/if Rahat wants to add Haiku, add a tiny `src/palimpsest/providers/haiku.py` subclassing AnthropicProvider with `name = "claude-haiku-4-5"` and `model = "claude-haiku-4-5"`. ~10 LOC. NOT in MVP scope.
- File `tests/test_slash_budget_cost.py` covers /budget update, /cost output format, /model unknown returns clear error.

## Verification
```bash
pixi run pytest tests/test_slash_budget_cost.py -v
pixi run tui
# /budget 75 → updates
# /cost → shows ledger summary
# /model haiku → returns "not implemented in MVP"
```

## Will touch
- `src/palimpsest/tui/slash.py` (edit: add 3 handlers)
- `tests/test_slash_budget_cost.py` (new)

## Will NOT touch
- cost.py (set_budget already in T05).
- agent.py.

## Out of scope
- Actually building haiku/deepseek/gemini providers (MVP is sonnet-only).
- /parser to pin a parser → low priority, defer unless requested.

## Notes / references
- Design ref: Appendix D slash command table.
- `/budget N` persists to SQLite settings table via `cost_meter.set_budget(N)` (already implemented in T05). The CostMeter reads `cap` from DB on every check, so the change takes effect immediately.
