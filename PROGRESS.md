# palimpsest progress

Append one line per merged task. Status markers: `✓` done, `⏳` in progress, `⏭` skipped, `🔁` redone.

## Week 1 — foundations

- ✓ T01 pixi init + lockfile — reproducible osx-arm64/linux-64 env; `pixi install` + `import palimpsest` verified (2026-05-26, 5404418)
- ✓ T02 repo skeleton — 7 stub modules + 5 subpackages + dir markers under `src/palimpsest/`; all imports ok (2026-05-26)
- ✓ T03 constitution + license — verified CLAUDE.md intact (6 grep checks); added MIT `LICENSE` + `AUTHORS.md` (2026-05-26)
- ✓ T04 anthropic provider — `AnthropicProvider` + `LLMResponse` wrap the Anthropic SDK (max_tokens 4096, ephemeral cache on system/tools); 2 live tests green, cache read 3203 tok. Model `claude-sonnet-4-6` per user (card said `-4-5`); in-test cost logging (CostMeter is T05) (2026-05-26)
- ✓ T05 cost meter — `CostMeter` + `BudgetExceeded` over SQLite (`cost_ledger`/`settings`, seed €50). `cap`/`soft` live-read for `/budget`; `record_llm`/`record_gpu`/`check_or_raise`/`set_budget` (refuses below spend). 5 offline tests green + persistence snippet ok. stdlib sqlite3, no new deps (2026-05-26)
- ✓ T06 agent loop — `Agent` (think→act→observe, 97 LOC) + `MaxTurnsExceeded`; module-level `TOOLS` registry + `@register` decorator. Meters each turn (check_or_raise €0.05, record_llm at Sonnet pricing ×0.92 EUR). Caches system+tools only when non-empty (empty block → 400). Logs `provider.name` (=`claude-sonnet-4-6`, not card's `-4-5`). Added `last_usage` so the cache test can read tokens. 3 tests green: no-tools→"pong", cache_read=3603 on 2nd run, max_turns raises (stub provider, deterministic) (2026-05-26)

## Week 2 — parsing & cache

## Week 3 — schema & extraction

## Week 4 — UI & viewer

## Week 5 — experiments & writing
