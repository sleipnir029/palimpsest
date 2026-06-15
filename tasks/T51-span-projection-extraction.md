# T51 — Span-projection + ID-citation extraction

## Why
`extract()` dumped raw parser JSON into the prompt and asked the LLM to echo a verbatim
`source_text` substring, which the T49 matcher fuzzy-matched to a span. Two failures:
- **Scale:** raw JSON is ~99% overhead (docling 4.86M tokens; paddle 216K > Sonnet).
- **Yield:** fuzzy matching is brittle (DeepSeek dropped a LaTeX `\,` → no match; 6/11 vs Sonnet
  14/14). A quoting-style difference the design shouldn't depend on.

## What changed
- **Project** each parser's geometry to numbered `(id, page, text, bbox)` spans (reuse `_spans_*`
  adapters). Show the LLM `[id] (p<page>) <text>`; it returns `evidence: {"spans": [id]}`.
- **Resolve** ids → union bbox + page + concatenated `source_text` (`_resolve_spans`). No fuzzy
  matching — equation/caption/table values become citable by id.
- **Adapter completeness:** capture mineru `content.math_content` (equations) + docling `tables`.
- **No-strip:** span text shown/stored verbatim (`_{Ir}`, `^{-1}`, `Co_{3}O_{4}` carry meaning).
- **Mis-citation guard:** value digits must appear in the cited span, else → errors.
- **One call over the full projection** (~18-25K tokens, fits any LLM) by default; **per-page
  batching only above `_MAX_PROJECTION_TOKENS`** (global ids) for very large papers.

## Decision log
- S4 was first set to always-per-page (user choice), then **reversed on live evidence**: per-page
  yielded 4-17 valid (high variance, 12 calls); a single call over the projection is consistent.
  Per-page's "room to avoid stripping" rationale was moot (~20K total).
- **Yield root cause:** the DeepSeek shortfall was not the matcher — the LLM emits Condition numeric
  fields as unit-bearing strings (`current_density: "10 mA cm-2"`) that fail Pydantic and discarded
  the whole measurement. `_coerce_floats` salvages them → stable 11-13 valid across runs.
- `_dedup` keys on `source_text` (not just value) so distinct catalysts at the same value are kept.

## Superseded / untouched
- Removed: `_resolve_bbox`, `_norm`, `_bbox_area`, `_MIN_SPAN_MATCH_CHARS`, `_inject_provenance`.
- Untouched: `schema/*`, `store.py`, `normalize.py` (units/enums), providers, agent.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest -q          # 125 passed / 7 skipped, 0 failures
pixi run pytest tests/test_extract.py --live -v -s   # DeepSeek single call
# 3 live runs: 11/12/13 valid, 0 errors, €0.0041 each (matches/exceeds Sonnet's 14)
```

## Open / future
- **docling tables** projection is synthetic-tested only (sample corpus has no tables) — verify on
  a table-bearing paper.
- bbox precision is parser-block-granularity (mineru spans are paragraph-level), not line-level.
- Live-verified on **mineru** only; dots/paddle/docling projections are unit-tested but not yet run
  end-to-end through a live LLM (they fit a single call on flash, so cheap to confirm later).
