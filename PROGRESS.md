# palimpsest progress

Append one line per merged task. Status markers: `✓` done, `⏳` in progress, `⏭` skipped, `🔁` redone.

## Week 1 — foundations

- ✓ T01 pixi init + lockfile — reproducible osx-arm64/linux-64 env; `pixi install` + `import palimpsest` verified (2026-05-26, 5404418)
- ✓ T02 repo skeleton — 7 stub modules + 5 subpackages + dir markers under `src/palimpsest/`; all imports ok (2026-05-26)
- ✓ T03 constitution + license — verified CLAUDE.md intact (6 grep checks); added MIT `LICENSE` + `AUTHORS.md` (2026-05-26)
- ✓ T04 anthropic provider — `AnthropicProvider` + `LLMResponse` wrap the Anthropic SDK (max_tokens 4096, ephemeral cache on system/tools); 2 live tests green, cache read 3203 tok. Model `claude-sonnet-4-6` per user (card said `-4-5`); in-test cost logging (CostMeter is T05) (2026-05-26)
- ✓ T05 cost meter — `CostMeter` + `BudgetExceeded` over SQLite (`cost_ledger`/`settings`, seed €50). `cap`/`soft` live-read for `/budget`; `record_llm`/`record_gpu`/`check_or_raise`/`set_budget` (refuses below spend). 5 offline tests green + persistence snippet ok. stdlib sqlite3, no new deps (2026-05-26)

## Week 2 — parsing & cache

## Week 3 — schema & extraction

## Week 4 — UI & viewer

## Week 5 — experiments & writing
