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
