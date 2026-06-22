# T74 — Closing the extraction gap: multi-pass & ensemble vs single-shot

**Status:** done (2026-06-22) · **Group:** evaluation (thesis) · **Priority:** high

> **Banked (2026-06-22, benchmarking paused):** multi-pass benchmark executed
> (`experiments/llm_matrix_t74.py`, `multipass.py`, `reports/t74_report.html`).
> Headline: cheap model-union ≈ Sonnet recall at ~10× lower cost. The extraction
> guards (`normalize.PLAUSIBLE_MAX`, `rederive_milli_value`) are 5-paper-tuned —
> validate on T73, relax/revert rather than tune further (see commit c9c11c3).

## Bigger picture (read first)
T72 measured **single-shot** extraction and proved *where* recall is lost. Its 200
misses decompose into distinct quadrants (from `experiments/results/rescore.json`):

| Quadrant | ~Share | Cause | Fix that can actually work |
|---|---|---|---|
| `model_gap` | ~50% | value is in the parser text, model didn't take it | union-of-samples (stochastic) · re-query (systematic) · reason-then-format (format-induced) |
| `coverage_gap` | ~30% | value only in a figure (4 Tafel slopes; mineru/dots ceiling 90%) | parser-union; docling/paddle already 100% ceiling |
| `wrong_type` | ~7.5% | right number, wrong class label | prompt/scorer edge |
| `fp` | (sep.) | hallucination + gold thinness | precision filter |

The split is the design: **each arm attacks one quadrant.** "Send the PDF to a
vision model" only touches the 30% coverage gap, breaks provenance (no bbox), and
blows the cheap-tier economics — so it is *not* the move. The recall lives in the
50% model gap, and that is reachable with cheap multi-pass.

**Honesty constraint (carried into the report).** The 2024–26 literature cleanly
benchmarks **union-of-samples** as a recall win — but only for *stochastic* misses
(it cannot recover a *systematic* blind spot). The "tell-it-what-it-found,
ask-for-the-rest" loop is widely recommended but **not** cleanly benchmarked vs
single-shot — so T74 measuring it is itself a contribution, reported as proposed
method with a predicted mechanism, not a borrowed result. A third near-zero-cost
lever T72 didn't isolate: **reason-then-format ordering** (CRANE, ICML 2025;
dottxt) — forcing a cheap model to emit `value` before any reasoning silently
drops fields, and DeepSeek-flash is exactly the vulnerable tier.

## Why
Establish the thesis claim with evidence, not assertion: **cheap model + loop ≥
expensive model + single-shot**, at a fraction of the cost. T72 ranked models;
T74 tests whether the cheap winner's *remaining* misses are recoverable cheaply.

## Arms (same 5 papers / 40 gold tuples / same scorer as T72)

| Arm | What | Attacks | Cost |
|---|---|---|---|
| **A** baseline | single-shot — reuse cached T72 rows | — | €0 |
| **B** reason-then-format | output contract reordered: evidence/reasoning **before** `value` | format-induced model_gap | 1× |
| **C** union-of-k | sample k=3 at temp>0, **union** items (not majority-vote), `_dedup` | stochastic model_gap | 3× |
| **D** coverage re-query | pass 1, then 2nd call: "you found {types}; OER papers usually also report {missing} — extract or state absent" | systematic model_gap | 2× |
| **E** parser-union | merge best per-paper outputs across docling ∪ paddle | coverage_gap | reuse B–D |
| **F** judge filter | LLM-as-judge after union arms: each value checked vs its cited span, drop unsupported (drops, never adds) | fp / precision | +1×/item |

**Models — spend constraint (user, 2026-06-21):** only **DeepSeek + Gemini**
(paid + free) are spendable. Multi-pass arms B–F run on `deepseek-flash` +
`gemini-lite`; the judge (F) runs on the cheap tier too. Frontier (`gpt-5.4`,
`sonnet-4.6`) is the comparison baseline **from T72 cache only — never re-called.**

**Parsers:** `docling`, `paddle` (100% ceiling → isolates model skill). mineru/dots
kept only in E, to show parser-union closing the figure-Tafel coverage gap.

## New metric: reachable-recall
`reachable_recall = tp / (gold tuples the parser actually surfaced)` — recall
normalized by the coverage ceiling, isolating model skill from parser limits (the
thesis axis). Computable **€0** from `coverage.json` (`ceiling`, per-tuple
`present`) + `rescore.json` (`hit`). Anchor in the report to the established
lineage: oracle-normalized recall / Retriever Potential Attainment / SQuAD-2.0
answerable-subset recall — turns a local hack into a defensible contribution.

## Current situation (reuse, don't reinvent — none of this is new code)
- `experiments/ab_extract.py`: `GOLD` (40 tuples), `_score_preds`, `_matches` — scorer reused unchanged.
- `experiments/llm_matrix.py`: model×paper×parser loop, CSV row, archive, CostMeter gate — harness pattern.
- `experiments/extraction_cache.py`: `prompt_hash`-keyed cache; a new prompt/mode auto-branches.
- `src/palimpsest/tools/extract.py`: `_load_spans`, `_render_projection`, `_resolve_spans` (provenance), `_process_items`, `_dedup` — provenance `(paper_sha, parser, page, bbox, source_text)` flows through `_resolve_spans`; `_dedup` key already includes `source_text`, so union/merge is safe.
- `experiments/coverage.py`, `experiments/rescore.py`: ceiling + per-tuple taxonomy.

## What to build
1. `experiments/multipass.py` — thin wrappers over `extract()`:
   - `extract_union(paper, parser, model, k=3, temp=0.7)` → k× call, concat, `_dedup`.
   - `extract_requery(paper, parser, model)` → pass1; build missing-type prompt from found `type`s vs schema measurement classes; pass2; merge + `_dedup`.
   - `judge_filter(items, provider)` → per item, one cheap yes/no: does the cited span support value X? drop "no".
   - `parser_union(results_by_parser)` → merge + `_dedup`.
2. Arm **B** = a reordered `_build_system_prompt` variant behind a flag (new `prompt_hash`); production prompt untouched.
3. `experiments/llm_matrix_t74.py` (fork, keeps T72 snapshots reproducible) registering modes `reason-first`, `union-k3`, `requery` + post-passes `parser-union`, `judge`.
4. `reachable_recall` column on the CSV + small computation extending `rescore.py`.

**Caching is mandatory (non-negotiable).** T72 lost extractions when credits
drained because raw outputs weren't persisted. Every arm — each of the k=3 union
samples, both re-query passes, and the judge's per-item calls — persists raw LLM
output via `extraction_cache.py` (keyed by `prompt_hash` + arm/mode + sample idx)
**before** scoring. A re-run hits cache and re-scores at €0. Nothing is scored
from an unsaved call.

**Stop rule:** D and F get **one** extra pass each — no loop-until-dry. Cheap
models false-stop on "is anything missing?"; measure that, don't trust it.

## Verification
```bash
pixi run python experiments/llm_matrix_t74.py && test -f experiments/results/llm_matrix_t74_*.csv
pixi run python experiments/rescore.py   # reachable_recall ≤ 1.0; hits ≤ ceiling per cell
```
- Assert arm A reproduces cached T72 numbers exactly (scorer regression).
- Spot-check 3 union/requery items: provenance dict present, `source_text` matches the cited span, value within tolerance (multi-pass didn't strip provenance).
- Confirm production `extract()` `prompt_hash` unchanged (arm B is flag-gated).

## Will touch
- `experiments/multipass.py` (new), `experiments/llm_matrix_t74.py` (new)
- `experiments/rescore.py` (add reachable_recall)
- `experiments/results/llm_matrix_t74_<date>.csv` + `.meta.json`, `results/extractions/` (generated)
- `experiments/results/FINDINGS.md` (new finding #5)

## Will NOT touch
- `src/palimpsest/tools/extract.py` production path (arm B is flag-gated; default prompt stable)
- `agent.py` / agent loop · the shipped `llm_matrix.py` (T72 reproducibility)

## Out of scope
- Re-calling frontier models (cached-only; no new GPT/Sonnet spend).
- Raw image→JSON vision extraction (breaks provenance; coverage gap handled by parser-union).
- Loop-until-dry / unbounded re-query (one extra pass, hard cap).
- Shipping any arm into the runtime — T74 is offline analysis; runtime stays single-shot until a result earns the change.
