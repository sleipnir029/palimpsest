# T50 — DeepSeek v4 flash as default LLM (+ T49 bbox loose ends)

> Backfilled card (2026-06-15). T50 shipped on 2026-06-13 but never got its own
> card; the authoritative record is the `PROGRESS.md` T50 entry. This card distills it.

## Why
Cost pivot. Anthropic Sonnet (~€0.29/paper) is too expensive for iterative extraction
runs, and the T49 live verification runs drained the palimpsest Anthropic account credit.
Switch the default runtime LLM to **`deepseek-v4-flash`** (~€0.0084/paper — ~35× cheaper).

## What changed
- **`DeepSeekProvider(AnthropicProvider)`** (`src/palimpsest/providers/deepseek.py`) —
  DeepSeek serves an **Anthropic-wire-compatible endpoint** (`https://api.deepseek.com/anthropic`):
  works with the `anthropic` SDK, returns Anthropic-shaped `usage` (so `_cost_eur` and the
  €50 cap hold), tool use works, `cache_control` accepted-and-ignored. So the provider just
  repoints `base_url` + model — **zero new deps, no agent-loop refactor**. `AnthropicProvider.__init__`
  gained `base_url`/`name` params.
- **Per-provider pricing:** `_cost_eur(usage, prices=None)` defaults to Sonnet (stubs unaffected);
  `DeepSeekProvider.prices` carries flash rates; `agent.py` + `extract.py` call sites pass
  `getattr(provider, 'prices', None)`. Defaults flipped to DeepSeek in `extract.py` (`_PROVIDER`)
  and `__main__.py`.
- **Two live-surfaced fixes:** (1) flash defaults extended thinking ON → variable reasoning-token
  spend truncated JSON unpredictably → `DeepSeekProvider.extra_request = {"thinking": {"type": "disabled"}}`.
  (2) `max_tokens` made configurable (Anthropic 4096, DeepSeek 8192) since the T49 verbatim-quote
  prompt makes the JSON larger.
- **Schema↔prompt mismatch (fixed properly, user-authorized scope expansion into schema):** the 5
  `normalize.UNIVERSAL_ENUMS` (`iR_correction` etc.) were advertised to the LLM but never modeled —
  DeepSeek emitted `condition.iR_correction` → Pydantic `extra_forbidden` → 0 valid (Sonnet happened
  to dodge it). Modeled all 5 as LinkML enum slots on `Condition`, regenerated `schema/generated/*`;
  `test_universal_enums_match_schema` pins the sync.
- **modeled → persisted (independent-review catch):** `store.py`'s `_add_condition` had a hardcoded
  scalar table that silently dropped the new enum slots. Added the 5 enum rows + `_add_scalars`
  unwraps `Enum → .value`; verified end-to-end via SPARQL (`palimpsest:iRCorrection → "applied"`).
- **`_schema_without_bbox()`** strips the 4 `bbox_*` slots from the Evidence def shown to the LLM
  (bbox is resolved from parser geometry at runtime; validation/store use the real schema unchanged).
- **T49 loose end (Q4):** `test_per_parser_bbox_pipeline` runs dots/paddle/docling synthetic geometry
  through `_load_spans` → `_resolve_bbox` — the only feasible check for docling (4.86M tok) / paddle
  (217K), too big to feed extraction whole (extraction-input chunking flagged as a separate future task).

## Results
- Offline: `pixi run pytest` → **122 passed / 7 skipped, 0 failures** (paid live tests, incl. the
  Anthropic-specific ones, marked `@pytest.mark.live` so a dead Anthropic key can't fail the suite).
- Live (DeepSeek, user-authorized): `test_extract --live` → 6 valid / 5 errors, **€0.0084** (real OER
  values 236/298/412 mV, Tafel 52.6/75.8/109.8 mV/decade; parser-native bboxes; units + `iR_correction`
  validated — the 5 errors are quotes matching no parser span, honestly routed to errors).
  `test_e2e --live` (agent loop + tool-calling through the compat endpoint) → PASS.

## Deviation from CLAUDE.md locked stack
CLAUDE.md said "Anthropic primary, DeepSeek fallback only". User explicitly chose to **replace
Anthropic as the default**; `AnthropicProvider` is KEPT as fallback (not deleted), runtime default
is DeepSeek. CLAUDE.md line 38 now reflects this.

## Files
- `src/palimpsest/providers/deepseek.py` (new), `providers/anthropic.py` (`base_url`/`name` params),
  `agent.py` + `tools/extract.py` (per-provider pricing, default flip), `__main__.py` (default flip),
  `schema/palimpsest.yaml` + `schema/generated/*` (5 Condition enum slots), `store.py` (persist enums),
  `normalize.py`, tests (`test_e2e`, `test_extract`, `test_store`, enum-sync test).
- NOT touched: `cache.py`, `parsers/`, the agent loop structure.

## Open / future
- Whether to make **pro** the default extraction model (cost vs recall) — see T52; user call.
- Extraction-input chunking for parsers whose raw output exceeds context (docling/paddle) — separate task.
