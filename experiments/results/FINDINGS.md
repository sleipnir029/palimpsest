# palimpsest — research findings log

Durable, accumulating log of benchmark/experiment findings (distinct from
`PROGRESS.md`, which is engineering progress). Each finding cites the raw data
snapshot it is built from (the stamped `llm_matrix_<parser>_<date>.csv` +
`.meta.json` in this directory) so it can be re-checked later and reused in the
thesis. Newest findings appended at the bottom.

---

## Metric glossary (read once)

The scorer (`experiments/ab_extract.py:_score`) compares each model's extracted
measurements against the hand-built gold list. A **match** = same measurement
*type* (e.g. `Overpotential`) **and** the number within ±1% (±0.5 for small
integers).

- **TP** (true positives) — extractions that match a gold value ("got it right").
- **gt_total** — how many gold values exist for that paper (recall denominator).
- **n_valid** — how many measurements the model emitted that passed validation
  (precision denominator).
- **Recall = TP / gt_total** — of all correct answers that existed, what fraction
  did the model find? → **completeness**. 100% = missed nothing.
- **Precision = TP / n_valid** — of everything the model reported, what fraction
  was actually correct? → **trustworthiness**. Low = it invents/garbles values.
- **F1 = 2·P·R / (P+R)** — single 0–1 score, high only when *both* recall and
  precision are high. The best single "overall quality" number; it punishes a
  model that dumps every number (high recall, low precision) or plays it safe
  (high precision, low recall).
- **eur_per_tp (€/correct)** — `eur_per_paper / TP` = **cost per correct
  measurement**. The real production economics: cheap-but-wrong is expensive per
  *useful* result. This is the number to optimise.
- **µrecall / µf1** — plain average across the papers. **micro-recall** = total TP
  ÷ total gold across all papers (weights bigger papers more).

---

## Finding 1 — Stage-1 model selection on mineru (2026-06-20)

**Data:** [`llm_matrix_mineru_2026-06-20.csv`](./llm_matrix_mineru_2026-06-20.csv)
· meta: [`…meta.json`](./llm_matrix_mineru_2026-06-20.meta.json)
**Setup:** parser = **mineru** only · 5 gold papers (41 numeric tuples) · 10 models
producing rows · modes: **raw** (all) + **strict** json_schema (the 4 OpenRouter
rows only) · git `d85fd14` · budget €3.04 → €6.42 (run +€3.38) · prompt_hash
`bd526972a038`.

Raw = the production extraction path (plain JSON + Pydantic), so the raw numbers
are what shipping each model would actually deliver. Sorted by µf1 (quality),
with cost alongside.

### Results — raw mode (production-faithful)

| Model | µrecall | µf1 | micro-recall | €/correct | €total (5 papers) |
|---|---|---|---|---|---|
| gemini-3.1-flash-lite (`gemini-lite`) | 79.6% | **0.76** | 82.9% | **€0.0012** | €0.040 |
| qwen3.7-plus (`qwen-plus`) † | 79.2% | **0.76** | 84.8% | €0.0024 | €0.068 |
| sonnet-4.6 | 80.5% | **0.76** | 85.4% | €0.0166 | €0.580 |
| **deepseek-pro** | **83.3%** | 0.73 | **87.8%** | **€0.0017** | €0.063 |
| opus-4.8 | 78.3% | 0.69 | 85.4% | €0.0338 | €1.182 |
| gpt-5.4 (`openai-frontier`) | 82.1% | 0.68 | 85.4% | €0.0117 | €0.411 |
| gemini-3.5-flash (`gemini-free`) | 73.3% | 0.65 | 78.0% | **€0** (free) | €0.000 |
| haiku-4.5 | 71.6% | 0.62 | 73.2% | €0.0062 | €0.185 |
| gpt-5.4-mini (`openai-mini`) | 62.6% | 0.56 | 61.0% | €0.0046 | €0.115 |
| **deepseek-flash** | **33.9%** | **0.27** | 51.2% | €0.0010 | €0.020 |

† qwen-plus = **4 papers** (1 cell lost to an OpenRouter network drop), so its
averages aren't strictly comparable to the 5-paper rows.

### Results — strict json_schema mode (OpenRouter rows only), vs raw

| Model | µf1 raw → strict | µrecall raw → strict |
|---|---|---|
| gpt-5.4 | 0.68 → **0.71** | 82.1% → 85.0% |
| gpt-5.4-mini | 0.56 → **0.59** | 62.6% → 71.2% |
| qwen3.7-plus | 0.76 → **0.59** | 79.2% → 57.1% |
| gemini-3.1-flash-lite | 0.76 → **0.52** | 79.6% → 44.5% |

### Key findings

1. **The locked production default (`deepseek-v4-flash`, T50) is the worst model
   here** — 0.27 F1, and **0% recall on 3 of 5 papers** (it returned nothing).
   On mineru it is not fit as the default.
2. **Best value:** `deepseek-pro` (0.73 F1, 87.8% micro-recall, €0.0017/correct)
   and `gemini-3.1-flash-lite` (0.76 F1, €0.0012/correct). `gemini-3.5-flash` is
   **free** at 0.65 F1 — a strong €0 baseline.
3. **The expensive ceiling bought nothing.** `opus-4.8` (€0.0338/correct, 20× the
   cheap models) scored *below* deepseek-pro and sonnet. This empirically
   justifies the "measure once, then prune" decision — and the prune.
4. **Strict json_schema net-hurt the cheap models** (gemini 0.76→0.52, qwen
   0.76→0.59 µf1) and only marginally helped the GPTs. The rigid all-12-condition-
   slots schema makes weaker models drop valid extractions. **Do not ship strict
   mode for the cheap models.**

### Operational issues (not model quality)

- **`local` errored on all 5 papers**: `Request URL is missing an 'http://'`
  — `LOCAL_BASE_URL` in `.env` lacks the protocol prefix. Local floor unmeasured.
- **qwen-plus lost 1 cell** (paper bd9811a5): OpenRouter `RemoteProtocolError`
  (connection dropped). qwen is averaged over 4 papers, not 5.

### Caveats

- Paper **bd9811a5**'s mineru recall ceiling is **4/8**: its 4 figure-derived
  Tafel-slope gold values live only in docling/paddle text, not mineru — so they
  are unreachable by *every* model on mineru. This deflates that paper's recall
  uniformly across models (ranking stays valid; Stage-2 on other parsers should
  recover them — this is the parser-conditional point).
- Gold is 4-parser **consensus** (`experiments/ground_truth_*.md`), not an oracle.

### Decisions taken

- **Drop `opus-4.8`** from the roster (cost, no accuracy gain).
- **Keep every other model** — including `deepseek-flash` — for **Stage-2**, to
  see how each behaves on the *other* parsers (docling/dots/paddle). A model weak
  on one parser may be strong on another.
- **Defer** any change to the locked `deepseek-v4-flash` runtime default until
  Stage-2 shows whether it recovers off mineru.
- Strict-mode arm: keep in code; revisit whether to run it in Stage-2 (it hurt
  the cheap models here).

---

## Finding 2 — Stage-2 docling sweep + mineru-vs-docling (2026-06-20)

**Data:** [`llm_matrix_docling_2026-06-20.csv`](./llm_matrix_docling_2026-06-20.csv)
· meta: [`…meta.json`](./llm_matrix_docling_2026-06-20.meta.json) (git commit +
budget recorded there). **Setup:** parser = **docling** · same 5 gold papers (41
tuples) · 10 models · raw + strict (4 OpenRouter rows) · budget €6.42 → €9.17
(run +€2.74). Compared against Finding #1 (mineru). Raw mode = production-faithful.

### mineru → docling, per model (raw mode)

| Model | µF1 | micro-recall (tp/41) | €/correct | trend |
|---|---|---|---|---|
| deepseek-flash | 0.27 → 0.63 | 51% → 88% (21→36) | €0.0010 → €0.0007 | ⬆ **rescued** |
| gemini-3.1-flash-lite | 0.76 → 0.86 | 83% → 93% (34→38) | €0.0012 → €0.0014 | ⬆ best overall |
| gemini-3.5-flash (free) | 0.65 → 0.75 | 78% → 88% (32→36) | €0 | ⬆ |
| sonnet-4.6 | 0.76 → 0.78 | 85% → 95% (35→39) | €0.0166 → €0.0184 | ⬆ top recall, 10× cost |
| gpt-5.4 | 0.68 → 0.74 | 85% → 90% (35→37) | €0.0117 → €0.0135 | ⬆ |
| gpt-5.4-mini | 0.56 → 0.63 | 61% → 76% (25→31) | €0.0046 → €0.0048 | ⬆ |
| deepseek-pro | 0.73 → 0.73 | 88% → 88% (36→36) | €0.0017 → €0.0022 | = rock-steady |
| qwen3.7-plus | 0.76 → 0.73 | 85% → 85% (28/33→35/41) | €0.0024 → €0.0030 | = (lost 1 strict cell) |
| haiku-4.5 | 0.62 → 0.61 | 73% → 51% (30→21) | €0.0062 → €0.0108 | ⬇ **regressed** |

### Key findings

1. **The parser matters as much as the model.** docling raised raw micro-recall
   for **8 of 9** models. The same model+prompt swings 30+ points by parser alone
   — this is the thesis's parser-conditional-accuracy claim, demonstrated.
2. **`deepseek-flash` was rescued by docling** (0.27→0.63 µF1; 51%→88% micro-
   recall). Its Finding-#1 "worst model" result was a **parser artifact, not a
   model defect** — vindicating the decision to keep it past Stage-1 instead of
   pruning. (Still flaky: 0% on the small paper bd86866b, so µF1 < micro-recall.)
3. **Why docling lifts almost everyone:** it emits ~656 fine-grained spans vs
   mineru's coarse blocks, so figure/table-derived values become citable. The
   Finding-#1 "bd9811a5 mineru ceiling 4/8" is **gone** on docling (multiple
   models 0%→100% on that paper).
4. **`haiku-4.5` is the lone regressor** (73%→51% micro): it collapsed on the
   largest paper (11% recall on 3432d049) — docling's denser spans hurt it where
   they helped others. Not every model benefits from finer input.
5. **Best (parser, model) value so far:** `gemini-3.1-flash-lite` on docling
   (0.86 F1, 93% recall, €0.0014/correct); free `gemini-3.5-flash` on docling
   (88%, €0); `deepseek-pro` (rock-steady 88% both parsers). For max recall,
   `sonnet-4.6` on docling (95%) but ~10× the cost.
6. **Strict json_schema was less uniformly harmful on docling** than on mineru —
   it *helped* qwen/gpt-5.4-mini on several docling papers and hurt gemini-lite on
   the big one. So the raw-vs-strict effect is itself parser-dependent; raw stays
   the production comparison.

### Operational issues

- `local` errored ×5 again (`LOCAL_BASE_URL` still missing `http://` in `.env`).
- qwen-plus lost 1 **strict** cell to a `ReadTimeout` (raw is the full 5 papers).

### Decisions / open

- Production **(parser, model)** choice **deferred** until dots + paddle complete
  the 4-parser grid.
- The locked `deepseek-v4-flash` default is now defensible *on docling* (cheapest
  viable, €0.0007/correct) but inconsistent; `deepseek-pro` is the steadier pick.
  Decide after the full grid.

---

## Finding 3 — Stage-2 dots sweep + full three-parser comparison (2026-06-20)

**Data:** [`llm_matrix_dots_2026-06-20.csv`](./llm_matrix_dots_2026-06-20.csv) ·
meta sidecar. **Setup:** parser = **dots** · same 5 gold papers (41 tuples) ·
9 models scored · raw + strict · budget €10.11 → €12.20 (run +€2.09; **plus
~€0.94 wasted** on a first attempt that crashed on a null-value extraction — root
cause fixed in commit `3ef5742`, scorer + per-cell resilience). qwen lost both
its dots **strict** cells to OpenRouter timeout/protocol errors → **dropped from
future runs**.

### Three-parser comparison — raw mode (µF1 · micro-recall %), mineru / docling / dots

| Model | µF1 (min/doc/dots) | micro-recall (min/doc/dots) | best €/correct |
|---|---|---|---|
| gemini-3.1-flash-lite | 0.76 / **0.86** / 0.78 | 83 / **93** / 85 | €0.0011 |
| gemini-3.5-flash (free) | 0.65 / 0.75 / 0.75 | 78 / 88 / 88 | **€0** |
| deepseek-pro | 0.73 / 0.73 / 0.66 | 88 / 88 / 76 | €0.0017 |
| deepseek-flash | 0.27 / 0.63 / 0.67 | 51 / 88 / 80 | €0.0006 |
| sonnet-4.6 | 0.76 / 0.78 / 0.57 | 85 / **95** / 80 | €0.0166 |
| gpt-5.4 | 0.68 / 0.74 / 0.65 | 85 / 90 / 85 | €0.0109 |
| gpt-5.4-mini | 0.56 / 0.63 / 0.55 | 61 / 76 / 68 | €0.0039 |
| haiku-4.5 | 0.62 / 0.61 / 0.67 | 73 / 51 / 73 | €0.0059 |
| qwen3.7-plus † | 0.76 / 0.73 / 0.72 | 85 / 85 / 80 | €0.0023 |

† qwen dropped going forward (latency); its data is retained here.

**Per-parser best model (raw, micro-recall):** mineru → `deepseek-pro` 88% ·
docling → `sonnet-4.6` 95% (or `gemini-3.1-flash-lite` 93%, ~12× cheaper) ·
dots → `gemini-3.5-flash` (free) 88%.

### Key findings

1. **docling is the best parser overall** — most models peak there; **mineru is
   the weakest**, dots sits in between. The parser choice moves accuracy more than
   most model choices do.
2. **gemini models are the most parser-robust and cheapest:** free
   `gemini-3.5-flash` is steady (78/88/88% micro) at €0; `gemini-3.1-flash-lite`
   peaks on docling (0.86 F1, 93%, €0.0011). These are the production front-runners.
3. **`deepseek-flash` kept climbing off mineru** (0.27→0.63→0.67 µF1) — its
   Stage-1 "worst model" verdict was definitively a mineru artifact.
4. **Several models are parser-fragile:** `sonnet-4.6` collapses on dots
   (0.78→0.57 µF1, 0% on bd86866b), `deepseek-pro` dips on dots (88→76%), `haiku`
   is erratic (worst on docling, fine on dots). The parser×model interaction is
   real signal, not noise.

### Decisions / open

- **Emerging production pick: docling + `gemini-3.1-flash-lite`** (0.86 F1, 93%
  recall, €0.0011/correct) — or free `gemini-3.5-flash` on docling (88%, €0) if
  €0 outweighs the F1 gap. Confirm after paddle.
- `qwen3.7-plus` dropped from the roster (OpenRouter latency).
- `paddle` is the only parser left to close the 4-parser grid.
- `local` still unmeasured (`LOCAL_BASE_URL` missing `http://`).

---

## Finding 4 — paddle sweep + FULL 4-parser grid & production synthesis (2026-06-20)

**Data:** [`llm_matrix_paddle_2026-06-20.csv`](./llm_matrix_paddle_2026-06-20.csv)
· meta sidecar. **Setup:** parser = **paddle** · 5 gold papers · 8 models · raw +
strict · budget €12.20 → €14.03 (run +€1.83). qwen already dropped. **Anthropic
credits drained mid-run** → `sonnet-4.6` paddle is **partial (2/5 papers)** and
not comparable; `gemini-free` missed 1 paddle paper to a transient 503. The
per-cell resilience fix (`3ef5742`) let the run finish despite both.

### FULL grid — raw mode µF1 (mineru / docling / dots / paddle)

| Model | µF1 m/d/dt/p | micro-recall m/d/dt/p | avg µF1 † | €/correct |
|---|---|---|---|---|
| **gemini-3.1-flash-lite** | .76/.86/.78/.81 | 83/93/85/83 | **0.80** | €0.0011 |
| gemini-3.5-flash (free) | .65/.75/.75/.84 | 78/88/88/92 | 0.72 ‡ | **€0** |
| deepseek-pro | .73/.73/.66/.73 | 88/88/76/93 | 0.71 | €0.0017 |
| sonnet-4.6 | .76/.78/.57/(.88) | 85/95/80/(95) | 0.71 ‡ | €0.0166 |
| gpt-5.4 | .68/.74/.65/.64 | 85/90/85/78 | 0.67 | €0.0109 |
| haiku-4.5 | .62/.61/.67/.76 | 73/51/73/90 | 0.66 | €0.0059 |
| gpt-5.4-mini | .56/.63/.55/.57 | 61/76/68/85 | 0.58 | €0.0039 |
| deepseek-flash | .27/.63/.67/.31 | 51/88/80/59 | **0.47** | €0.0006 |

† avg over parsers where the model ran all 5 papers. ‡ gemini-free = 3/4 parsers
(503 on one paddle paper); sonnet = 3/4 (paddle partial, shown parenthesised).

### paddle — per-model detail (raw), including the partial sonnet row

Standalone paddle scores. **`sonnet-4.6` ran only 2/5 papers** (Anthropic credit
exhausted mid-run); its row is shown as-collected but is an optimistic partial —
**not comparable** to the full-5 rows. `gemini-free` = 4/5 (one 503).

| Model | papers | µrecall | µF1 | micro-recall | €/correct |
|---|---|---|---|---|---|
| sonnet-4.6 * | 2/5 | 83% | 0.88 | 95% (21/22) | €0.0130 |
| gemini-3.5-flash (free) * | 4/5 | 85% | 0.84 | 92% (34/37) | €0 |
| gemini-3.1-flash-lite | 5/5 | 84% | 0.81 | 83% (34/41) | €0.0012 |
| haiku-4.5 | 5/5 | 87% | 0.76 | 90% (37/41) | €0.0054 |
| deepseek-pro | 5/5 | 88% | 0.73 | 93% (38/41) | €0.0017 |
| gpt-5.4 | 5/5 | 71% | 0.64 | 78% (32/41) | €0.0129 |
| gpt-5.4-mini | 5/5 | 81% | 0.57 | 85% (35/41) | €0.0037 |
| deepseek-flash | 5/5 | 34% | 0.31 | 59% (24/41) | €0.0009 |

`*` partial coverage (see above). sonnet-4.6 paddle per-paper: `3432d049` r=100%
F1=0.95 · `bd86866b` r=67% F1=0.80 (the only two it completed before the 400s).

On full-5-paper coverage, **deepseek-pro leads paddle recall (93%)**, haiku is
unexpectedly strong (90%), free gemini-flash is excellent value (92%, €0), and
deepseek-flash collapses again (59%) — the same parser-fragility it shows on mineru.

### Per-parser winner (raw, micro-recall, full-5-paper models only)

| Parser | Best | | Cheap alternative |
|---|---|---|---|
| mineru | deepseek-pro | 88% | gemini-lite 83% |
| docling | sonnet-4.6 | 95% | gemini-lite 93% (~12× cheaper) |
| dots | gemini-3.5-flash (free) | 88% | — (€0) |
| paddle | deepseek-pro | 93% | gemini-free 92% (€0) |

### Synthesis — the production decision

1. **Best overall model: `gemini-3.1-flash-lite`.** Highest *and* most consistent
   (0.80 avg µF1, every parser 81–93% recall) at €0.0011/correct. Robustness
   across parsers is the deciding property for an autonomous agent that may run any
   parser.
2. **Recommended production combo: docling + `gemini-3.1-flash-lite`** (0.86 F1,
   93% recall, €0.0011/correct). If €0 outweighs the F1 gap: docling/paddle +
   free `gemini-3.5-flash` (88–92%, €0).
3. **`deepseek-pro` is the best parser-agnostic *paid* fallback** (76–93% on every
   parser) and a drop-in runtime change (same DeepSeek provider, `model=
   deepseek-v4-pro`).
4. **`deepseek-v4-flash` (the locked T50 default) should be replaced.** Worst
   overall (0.47 avg µF1), too parser-fragile to trust as the default; it only
   looks cheap until you price its misses (it found ~nothing on 3 mineru + 3
   paddle papers). See "open decision" below.
5. **Parser ranking:** docling ≳ dots ≈ paddle > mineru for ceilings, but the
   best model is parser-robust enough that the *model* choice matters more than the
   parser once you're off mineru.

### Operational / data-quality notes

- Anthropic credits drained → sonnet paddle partial (2 papers); top up to re-run
  if a full sonnet paddle row is wanted.
- `gemini-free` paddle = 4 papers (one 503); re-runnable for €0.
- `local` never measured (`LOCAL_BASE_URL` lacks `http://` in `.env`).
- bd9811a5 (the figure-Tafel paper) still caps recall on mineru/dots/paddle where
  those values aren't in the parse text; docling recovers them — a parser-coverage
  effect, uniform across models.

### OPEN DECISION (for the user)

Change the locked runtime default `deepseek-v4-flash` (T50) → either
`deepseek-v4-pro` (safe drop-in, steady ~88%) or `gemini-3.1-flash-lite` (best
overall, needs the runtime pointed at the Gemini provider). Deferred to the user;
this is a CLAUDE.md-locked default, so it changes only on explicit approval.

---

## Finding #5 — T74: multi-pass & ensemble vs single-shot (cheap tier)

*Data: `llm_matrix_t74_2026-06-21.csv` (+`.meta.json`), `reachable.json`,
`rescore.json` (285 cells), git d8b411f. Spend +€0.67 (DeepSeek+Gemini only;
frontier rows are cached T72 single-shot, never re-called). 6 arms on docling+paddle
(100% ceiling), 5 gold papers. Arms A (raw) and E (parser-union) are €0 cache-derived.*

**New metric — reachable-recall** = `hit / (gt_total − coverage_gap)`: recall
normalized by what the parser actually surfaced, isolating model skill from parser
limits (lineage: oracle-normalized recall / Retriever Potential Attainment /
SQuAD-2.0 answerable-subset). Computed €0 in `reachable.py` from `rescore.json`.

### Headline: cheap + loop ≥ expensive + single-shot — SUPPORTED, but conditional

| combo | recall | cost vs frontier |
|---|---|---|
| **gemini-lite + union-k3 (docling)** | **98%** (39/40) | = sonnet-4.6 single-shot (98%), **~12× cheaper** |
| **gemini-lite + requery (docling)** | **98%** (39/40) | > openai-frontier single-shot (88%) |
| gemini-lite raw (docling) | 92% | already > openai-frontier (88%) |
| deepseek-flash + any loop | 72–95% | does NOT reach frontier via these loops |

A *good* cheap model (gemini-3.1-flash-lite) + a cheap loop **matches frontier
single-shot** on the best parser. The *ultra*-cheap model (deepseek-v4-flash) does
**not** close the gap with loops — consistent with Finding #4's "replace the flash
default". The thesis claim holds for the right cheap model, not unconditionally.

### Per-arm verdict (each attacks one T72 miss quadrant)

- **union-k3 (stochastic model_gap).** Modest, model/parser-dependent: gemini-lite
  docling **92→98** (+6, recovered 2–3 stochastic misses), paddle 92=92;
  deepseek-flash paddle **72→78** (+6), docling 95→92 (slight loss, low-variance
  baseline). Union helps where there is stochastic headroom; can't manufacture it.
  Matches the literature (union recovers stochastic misses only).
- **requery (systematic model_gap — the UNbenchmarked loop; T74's contribution).**
  Two-faced: **helped the stronger cheap model** (gemini-lite docling 92→**98**, the
  best single result) but **hurt the weaker one** (deepseek-flash docling 95→90,
  paddle 72→68). Confirms the predicted failure — a cheap model asked "what did you
  miss?" mis-extracts/false-stops. **Not a free win; can degrade the weakest model.**
- **reason-first (format-induced; CRANE/dottxt).** **Backfired catastrophically on
  the cheapest model**: deepseek-flash docling **95→40** (the reasoning field eats
  the 8192-token output budget → truncated items). Neutral elsewhere (gemini-lite
  92=92 / 92→90). **Reason-then-format does NOT transfer to a token-budget-limited
  cheap model** — the one place naive CRANE application is most tempting.
- **parser-union (coverage_gap).** The clean coverage win: **deepseek-flash recovers
  the figure-Tafel paper 4/8→8/8** and reaches **recall 1.0 on 4/5 papers** by
  unioning raw cells across all 4 parsers — the values absent from any single text
  parser are recovered from a figure-aware one. *Precision caveat:* `dedup_by_value`
  collapses on exact (type,value) while the scorer matches within ±1%, so
  near-duplicate cross-parser values survive as FPs and **deflate parser-union
  precision** (0.28–0.95) — the recall/coverage claim is sound, precision is a
  lower bound (see N2).
- **judge (precision filter, DROP-only).** Near-no-op here: recall preserved
  (union-k3→judge: 37=37, 31=31, 39→38, 37=37 — DROP-only invariant held) but
  precision barely moved (0.45→0.46, 0.56→0.57, 0.73=0.73). A cheap judge rarely
  refutes a numeric value, and the high FP count (406 grid-wide) is mostly
  **gold-thinness** (real values the gold omits), which a judge cannot fix.

### Honest caveats
- Recall is the trustworthy axis; precision on union/parser-union is understated by
  exact-vs-tolerant dedup (N2) and gold-thinness — don't headline arm-E precision.
- T74 measures the *cheap tier*; frontier is T72-cached single-shot (no multi-pass
  frontier arm — out of scope and out of the DeepSeek+Gemini spend fence).
- One transient OpenRouter/Gemini stall during the run; resumed from cache at €0
  (every paid call — each union sample, each requery pass, the judge — is persisted).

### Takeaway for the thesis
"Cheap + loop beats expensive + single-shot" is **true for the right cheap model and
the right loop** (gemini-lite + union/requery on docling = frontier, ~12× cheaper),
and **parser-union is the reliable coverage closer**. But multi-pass is **not a free
lunch**: reason-first can be catastrophic and requery can hurt the weakest model —
the loop must be matched to the model, which is itself the nuance worth reporting.

### Finding #5 addendum — model-union, reason-first retest, gold-thinness

*Added after a follow-up round (+€0.15; `llm_matrix_t74.csv` now 140 rows,
`gold_thinness.json`, refreshed `reachable.json`/`rescore.json`).*

**Arm G — model-union (cheap ∪ cheap, single-shot each). THE standout, and €0.**

| parser | model-union | precision | best frontier single-shot |
|---|---|---|---|
| **docling** | **100% (40/40)** | 0.71 | sonnet-4.6 98%, openai-frontier 88% |
| **paddle** | **95% (38/40)** | 0.66 | sonnet-4.6 95%, openai-frontier 75% |

deepseek-flash ∪ gemini-lite, one shot each, unioned → **beats the best frontier
model on docling, ties it on paddle**, because the two cheap models miss *different*
values (decorrelated errors). Cleaner than the within-model loops (union-k3/requery)
and than parser-union (precision 0.71 vs 0.28–0.95 — only 2 sources, fewer FPs).
This is the strongest support for "cheap + ensemble ≥ expensive single-shot", and it
reuses cells already paid for — marginal cost €0.

**Reason-first retest (was the catastrophe truncation?).** Partly. deepseek-flash
docling: reason-first @8k **40%** → @16k **75%** — raising the output cap recovered
most of the collapse (the reasoning field had been eating the items JSON). BUT 75% is
**still below plain raw (95%)**. So: truncation caused the *catastrophe*, but
reason-then-format **genuinely underperforms plain extraction** for this cheap model
even with adequate tokens. gemini-lite unaffected throughout (92%). Verdict: CRANE's
reason-before-format does NOT transfer to cheap *extraction* models — at best neutral,
at worst harmful; not worth the tokens here.

**Gold-thinness audit (`gold_thinness.py`) — precision was understated.** Of 105
distinct FP (type,value,paper) groups across the grid, by cross-model agreement:
- **32 likely REAL** (≥3 independent models extract it, gold lacks it) — candidate
  gold additions, NOT model errors. Dominated by **measurement types the gold never
  scoped**: `PEMWECellVoltage` (1.939/1.986/2.0 V, 7 models agree) and
  `DegradationRate` (22/52/460 µV/h, 5 models) — real PEMWE metrics outside the
  original 8-class OER gold.
- 21 ambiguous (2 models); **52 likely hallucination** (1 model only) — the true
  precision loss.

So the "406 FPs" conflated ~30% gold-scope gaps with ~50% real hallucinations:
**precision is meaningfully understated**. NOTE (verified against `schema/palimpsest.yaml`):
the top "real" types — `PEMWECellVoltage`, `DegradationRate` — are **already in the
schema** (added T71). So the gap is **GOLD completeness, not the schema**: the cheap
models extract valid measurements the hand-built `ab_extract.GOLD` simply doesn't list.
Fix = extend GOLD, not the schema. Candidate additions (≥3-model agreement, with cited
spans, for human verification before folding in) → `results/gold_candidates_t74.md`.
Cross-model agreement is a label-free oracle for gold completeness — the
decorrelated-error principle that powers model-union, reused for QA. (Several candidates
will be rejected on review — e.g. `Stability 2.5`, the value the gold-audit deliberately
removed, and duplicate extractions of values already in GOLD — which is exactly why they
are proposed, not auto-added.)

**Updated thesis takeaway.** The best gap-closer is not a within-model loop — it is
**model-union of two cheap models** (docling 100%, paddle 95% = frontier, ~10× cheaper),
backed by **parser-union** for the figure-only coverage gap. Within-model passes are
modest and model-dependent (union-k3), two-faced (requery), or unhelpful (reason-first).
And a chunk of the apparent precision gap is gold-thinness, not model error.
