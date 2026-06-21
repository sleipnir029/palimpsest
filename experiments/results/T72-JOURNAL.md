# T72 — Lab journal: the parser×model extraction benchmark, start to finish

**What this file is.** A single narrative thread through the whole T72 experiment —
what I was trying to do, what I ran, what broke, how I fixed it, what new problems
each fix exposed, the corrected results, and *why* every methodological choice was
made. The other docs in this folder are the primary records; this one connects them:

- `FINDINGS.md` — the durable, dated findings log (the *what*, micro-F1 rankings).
- `gold_audit.md` — independent re-read of all 5 PDFs vs the gold (the *is-it-real*).
- `T72-error-analysis.md` — per-miss decomposition + scorer audit (the *why*).
- `coverage.json` / `rescore.json` — the machine artifacts those two are built on.
- `llm_matrix_<parser>_<date>.csv` (+ `.meta.json`) — the raw data snapshots.

Read this top to bottom and you should understand the entire arc without opening the
others. Where I quote a number, the source file is named so it can be re-checked.

> **One caution up front (read this before trusting any single number).** There are
> **two result snapshots** in this history and they disagree on purpose:
> - **2026-06-20** — the original Stage-1→Stage-2 runs, reported as micro-F1 rankings
>   in `FINDINGS.md`. Gold = **41 tuples**, `prompt_hash bd526972a038`.
> - **2026-06-21** — a *re-scoring* after the gold audit + coverage decomposition.
>   Gold = **40 tuples** (one dropped), `prompt_hash 9f23e7c683a0`, re-run for **€0**
>   from the extraction cache. This is the corrected view in `T72-error-analysis.md`.
>
> The numbers moved because the **inputs moved** (gold shrank, prompt hash changed),
> not because the experiment contradicts itself. Treat the 06-21 decomposition as the
> current truth and the 06-20 rankings as the path that got us there.

---

## 1. What T72 is and why it exists

**The thesis question this section answers.** palimpsest's thesis contribution is the
*constrained-autonomy agent*, not extraction accuracy. But one section has to defend a
real engineering choice: **does turning a research PDF into structured numbers actually
need a big, expensive model — or can a small/cheap one recover the same values?** And,
the sharper version: **how much of "accuracy" is the model at all, vs the PDF parser
that fed it?** That second question is the *parser-conditional accuracy* claim. T72 is
the experiment that puts numbers on both.

**The constraints that shaped the design (from `CLAUDE.md`):**
- **€50 hard cap** on everything palimpsest spends. CostMeter gates every paid call.
  This is why cost is a first-class axis, not an afterthought.
- **No LLM gateways in the runtime.** The agent/extraction/pipeline call providers
  directly. T72 got a *one-time, user-authorized carve-out* (2026-06-19) to route the
  non-Claude models through OpenRouter — but only in `llm_matrix.py`, offline analysis
  code. Claude still runs direct (OpenRouter marks Claude up 2×). No gateway touches
  `src/palimpsest/`.
- **Extraction is non-agentic.** `extract.py` calls `provider.complete(..., tools=None)`
  and parses JSON. Because there are no tool-calls to translate, a thin completion
  adapter per provider is enough — that's why adding OpenAI/Gemini for the benchmark
  was ~140 lines, not a framework.

---

## 2. Methodology and its scientific basis

This is the part worth understanding deeply, because the conclusions are only as good
as the measurement. Every choice below has a reason.

### 2.1 What the gold is
Per paper, a list of `(measurement_type, value)` tuples — e.g. `("Overpotential", 236)`
— keyed by the PDF's SHA-256. Transcribed from the 4-parser-consensus ground-truth
tables (`ground_truth_*.md`), not from a single parser's output, so the gold doesn't
secretly favor one parser. Five papers, originally 41 tuples (later 40).

### 2.2 Why deterministic matching, not an LLM judge
The scorer (`ab_extract.py:_score`) counts a **match** when the model emits the same
*type* AND a number within tolerance:

```
tol = max(|gold| * 0.01,  0.5 if |gold| >= 1 else 1e-4)
```

i.e. ±1%, with a ±0.5 floor for integers and a tight ±1e-4 for sub-unit values.
Matching is **greedy first-unmatched** (each prediction claims the first gold tuple it
fits). From those matches:

- **Recall = TP / gold_total** — completeness (did it miss anything?).
- **Precision = TP / n_predictions** — trustworthiness (is what it reported correct?).
- **F1 = 2PR/(P+R)** — one number, high only when both are.

**Why not DeepEval / an LLM-judge metric?** Two reasons, both in `llm_matrix.py`'s
rationale: (1) LLM-judge metrics are built for free-text/RAG answers, not numeric
extraction — here "correct" is a number within tolerance, which is *exactly* what a
deterministic check does best; (2) grading LLMs with an LLM is mildly circular and adds
cost and variance to the thing you're trying to measure. A tolerance check is
reproducible, free, and auditable.

### 2.3 Why cost is re-derived, not read from CostMeter
Reported as `eur_per_paper` and `eur_per_tp` (**€ per correct extraction** — the real
production economics: cheap-but-wrong is expensive per *useful* result). The cost is
recomputed from token counts × each provider's verified rate, **not** from CostMeter,
because CostMeter falls back to the Sonnet price for providers whose rates it doesn't
know — which would silently mis-price every non-Anthropic row. Per-paper prompt caching
is **disabled** during the benchmark so each paper's cost is honest and comparable.

### 2.4 The raw-vs-strict axis
Two output modes: **raw** (plain JSON → Pydantic, the actual production path) and
**strict** (`response_format=json_schema`, only the OpenRouter rows support it). Raw is
the production-faithful comparison; strict is a probe of whether schema-constraining
helps. (Spoiler from §3: it net-*hurt* the cheap models.)

### 2.5 Reproducibility
A `prompt_hash` is computed over skill body + schema + normalization rules +
measurement-class names. If any of those change, the hash changes, which (a) marks the
run as a different condition and (b) invalidates stale cache entries so you don't score
new prompts against old outputs. This is why the 06-20 and 06-21 snapshots carry
different hashes — the schema/normalization were touched between them.

---

## 3. Timeline — what I actually ran, stage by stage

### Stage 0 — harness lands (commit `d1ccef2`, 2026-06-19)
Built `llm_matrix.py` + two thin extraction-only adapters (`openai_compat.py`,
`gemini.py`; both **raise if handed tools** so they can never drive the agent loop).
First live result on **1 gold paper, 8/11 models**: DeepSeek-pro and Gemini-3.5-Flash
both hit **F1 0.97** (€0.014 / €0) and beat Sonnet + Opus. Early support for "no big
model needed." Some OpenRouter rows blocked by a 402 (no account credit yet). 324
offline tests green. *(Stage 0 is the one snapshot with no CSV/`FINDINGS.md` record —
its numbers are sourced from the `d1ccef2` commit message and aren't re-derivable from
data, unlike every later stage.)*

### Stage 1 — mineru, 10 models, 5 papers (commits `d85fd14` → `02a04c2`, 06-20)
Expanded gold to **5 papers / 41 tuples**, added the raw/strict axis and `eur_per_tp`,
parametrized the parser (default mineru) so Stage 2 is just `--parser=…`. Ran the full
roster on mineru. Budget €3.04 → €6.42 (+€3.38). Result, sorted by F1 (`FINDINGS.md`
Finding #1, raw mode):

| Model | µF1 | micro-recall | €/correct |
|---|---|---|---|
| gemini-3.1-flash-lite | 0.76 | 83% | €0.0012 |
| sonnet-4.6 | 0.76 | 85% | €0.0166 |
| **deepseek-pro** | 0.73 | **88%** | €0.0017 |
| opus-4.8 | 0.69 | 85% | €0.0338 |
| gpt-5.4 | 0.68 | 85% | €0.0117 |
| gemini-3.5-flash (free) | 0.65 | 78% | **€0** |
| haiku-4.5 | 0.62 | 73% | €0.0062 |
| gpt-5.4-mini | 0.56 | 61% | €0.0046 |
| **deepseek-flash** | **0.27** | 51% | €0.0010 |

**The shock:** `deepseek-v4-flash` — the *locked production default* (T50) — was the
**worst model**, 0.27 F1 with **0% recall on 3 of 5 papers** (it returned nothing).
And **opus-4.8, at 20× the cost, scored below deepseek-pro and sonnet** — the expensive
ceiling bought nothing. Strict mode net-*hurt* the cheap models (gemini 0.76→0.52).

**Decisions taken (`DEVIATIONS.md`, 06-20):** drop only **opus-4.8** (cost, no gain);
**keep deepseek-flash** despite being worst — because mineru has a known coverage
ceiling and the whole hypothesis is that a weak-on-one-parser model may be strong on
another; **defer** changing the locked default until Stage 2 proves whether flash
recovers. (This restraint turned out to be the right call — see Stage 2A.)

### Stage 2A — docling (commit `8ac02da`, 06-20)
Same roster on docling. Budget €6.42 → €9.17 (+€2.74). The headline (`FINDINGS.md` #2):

- **deepseek-flash rescued: 0.27 → 0.63 µF1, 51% → 88% micro-recall.** Its "worst model"
  verdict was a **parser artifact, not a model defect** — vindicating keeping it.
- **docling lifted 8 of 9 models.** It emits ~656 fine-grained spans vs mineru's coarse
  blocks, so figure/table values become citable. The same model+prompt swings 30+
  points by parser alone — *the parser-conditional claim, demonstrated.*
- **haiku-4.5 was the lone regressor** (73% → 51%): docling's denser spans *hurt* it on
  the biggest paper. Finer input is not universally better.

### Stage 2B — dots, then paddle (commits `2e73bdd`, `9e6471f`, `579c5f2`, 06-20)
Closed the 4-parser grid. dots: budget → €12.20 (+€2.09). paddle: → €14.03 (+€1.83).
Full grid, raw-mode avg µF1 across the four parsers (`FINDINGS.md` #4):

| Model | mineru / docling / dots / paddle (µF1) | avg µF1 | €/correct |
|---|---|---|---|
| **gemini-3.1-flash-lite** | .76 / .86 / .78 / .81 | **0.80** | €0.0011 |
| gemini-3.5-flash (free) | .65 / .75 / .75 / .84 | 0.72 ‡ | **€0** |
| deepseek-pro | .73 / .73 / .66 / .73 | 0.71 | €0.0017 |
| sonnet-4.6 | .76 / .78 / .57 / (.88) | 0.71 ‡ | €0.0166 |
| gpt-5.4 | .68 / .74 / .65 / .64 | 0.67 | €0.0109 |
| haiku-4.5 | .62 / .61 / .67 / .76 | 0.66 | €0.0059 |
| gpt-5.4-mini | .56 / .63 / .55 / .57 | 0.58 | €0.0039 |
| deepseek-flash | .27 / .63 / .67 / .31 | **0.47** | €0.0006 |

‡ partial parser coverage (see Stage-2 warts below). The 06-20 conclusion: best overall
model = **gemini-3.1-flash-lite** (most consistent), recommended combo = **docling +
gemini-3.1-flash-lite**; the locked **deepseek-flash is worst overall and should be
replaced** — but that's a CLAUDE.md-locked default, deferred to the user.

---

## 4. The warts — what broke and how I fixed it

Three failures, each of which forced a real change to the harness.

### 4.1 Null-value scorer crash (mid-dots run → fix `3ef5742`)
A model returned a null-valued extraction; the scorer crashed mid-run, taking the whole
sweep down. Fix `3ef5742` added **null handling + per-cell resilience**: one bad cell
now logs and is skipped instead of killing the run. **Cost of the lesson: ~€0.94 of
already-paid extractions wasted** on the crashed attempt before the re-run.

### 4.2 Anthropic credits drained (mid-paddle)
Anthropic credit ran out partway through the paddle sweep. `sonnet-4.6` completed only
**2/5 papers**; a transient 503 cost `gemini-free` one paper. Because the per-cell
resilience fix (4.1) was already in, the run **finished with the data it had** instead
of losing everything. The partial sonnet row is recorded but flagged **optimistic and
not comparable** to the full-5 rows — an honesty marker, not a result.

### 4.3 The data-loss lesson → `extraction_cache.py`
The original matrix scored each `extract()` call and **threw the extracted measurements
away**, keeping only the aggregate CSV row. When credits drained, the haiku/sonnet
outputs I'd *paid for* were gone for good. Fix: `extraction_cache.py` now persists the
**full** output of every paid call (items + errors + tokens + latency), keyed by
`(paper_sha, parser, label, mode, prompt_hash)`, one JSON per cell under
`extractions/`. A cache hit re-scores with **no API call**. This is the
`[[cache-every-paid-llm-output]]` rule, learned the expensive way. It's also what makes
the entire §5 correction pass cost €0.

---

## 5. The correction pass — re-scoring and decomposition (the scientific turn)

This is the most important part. After the grid was "done," the headline question was:
*we called those numbers the ground truth — but were they actually ground?* So I did
three things, all €0 because of the cache: re-read the PDFs (`gold_audit.md`), measured
what each parser's text can even reach (`coverage.py`), and decomposed every single miss
into its cause (`rescore.py`). The result reframes most of §3.

### 5.1 Recall was hiding three different failures
A missed gold tuple can mean three unrelated things, and only one is about the model:

```
gold tuple not found  ⇒  (a) value never in the parser's text   → coverage ceiling (parser)
                          (b) value present, wrong class label   → scorer artifact (type-strict)
                          (c) value present, simply not extracted → model gap (the real signal)
```

Conflating (a)/(b)/(c) is why the 06-20 findings could only say "parser-fragile." The
re-score separates them.

### 5.2 Gold audit — the numbers are real, the matching is meaning-blind
Independent re-read of all 5 PDFs (`gold_audit.md`):

- **All 41 numbers are genuinely in their papers. None fabricated, none numerically
  wrong** (within 1%). The benchmark is not built on invented data.
- **But gold is bare `(type, value)` — catalyst and condition stripped.** So
  semantically loaded numbers collapse to interchangeable digits: paper 2's "40 h" is
  the *reference (unsupported) IrO₂'s failure time*, not an achievement; paper 1's "6 h"
  is a *different 50 mA/cm² test*; paper 4's "1600 h" is a *scale-up De Nora cell*. The
  scorer can't tell right-number-wrong-context apart.
- **One genuine mislabel:** paper 5's `("Stability", 2.5)` — the text says both samples
  are "stable for 20 cycles and 2.5 h of operation," a *measurement-window
  reproducibility* note, **not a durability test.**
- **Thinness:** gold omits in-scope measured values on papers 3 and 5, so models that
  extract real-but-unlisted numbers are punished as false positives → **precision is
  understated.**

### 5.3 Coverage ceiling — the parser ranking is basically one figure
For each (parser, paper, value), does the value's literal form appear in the exact text
the LLM was shown? (`coverage.py`, validated by direct grep of the parse caches.)

| parser | coverage ceiling | cannot reach |
|---|---|---|
| docling | **40/40 = 100%** | — |
| paddle | **40/40 = 100%** | — |
| mineru | **36/40 = 90%** | the 4 figure Tafel slopes in `bd9811a5` |
| dots | **36/40 = 90%** | the same 4 |

The four values `45.16 / 46.25 / 48.29 / 51.78 mV/dec` exist **only as typeset labels
inside Fig 3b** of paper 4 — present in docling+paddle (which recover figure vector
text), absent from mineru+dots. So **on mineru/dots no model can exceed 90%** — 4 tuples
are physically unreachable. The whole parser ranking docling≈paddle > mineru≈dots is, at
the ceiling level, *entirely* this one paper's figure values. Everything else is
100%-covered everywhere.

### 5.4 The gold fix and its effect
**Dropped `("Stability", 2.5)` from `bd86866b`** (the one clear correctness fix). Gold
41 → 40. Re-scored from cache (€0): this single removal **deleted 24 spurious
`model_gap`s** across the grid — the models had *correctly* declined to call a
non-durability number "Stability," and the gold error had been masquerading as model
failure. `deepseek-pro` then reaches a clean **100% on docling**. The other audit items
(attribution-loaded tuples, thinness) are **documented but not changed** — fixing them
would alter the task definition rather than correct an error, so they stay as caveats.

### 5.5 The error taxonomy — decomposing every miss
Full 4-parser grid re-scored tuple-by-tuple (`rescore.py`, raw mode, 40-tuple gold).
Per-cell hit/wrong-type/coverage-gap/model-gap/false-positive (`T72-error-analysis.md`
§5, full table there). Grid totals over full-roster cells (gemini-free excluded as
partial): **1120 gold-slots, 920 hits (82%), 200 misses —**

| cause of miss | count | share | meaning |
|---|---:|---:|---|
| **model_gap** (present, not extracted) | **143** | **72%** | the genuine model signal |
| **coverage_gap** (not in the parse) | 56 | 28% | *all* 56 = the 4 Tafels × 14 mineru/dots cells; **zero** on docling/paddle |
| **wrong_type** (right value, wrong class) | **1** | **<1%** | scorer type-strictness is a non-issue |
| false positives (incl. thinness) | 401 | — | dominated by real values gold omits, not hallucination |

**What this proves:**
1. **The parser×model interaction is real and it lives in `model_gap`, not coverage.**
   Strip the uniform 4-tuple ceiling and the swings remain — genuine extraction
   differences.
2. **It's span-granularity × model-capability, cutting both ways:**
   - **deepseek-flash** starves on mineru's coarse blocks (13 model-gaps, 57%) but
     thrives on docling's fine spans (95%) — its "worst model" verdict quantified and
     dismissed as a mineru artifact.
   - **haiku-4.5** is the mirror: it **drowns in docling's ~656 dense spans** (15
     model-gaps, 60%) yet is fine on mineru (85%) and paddle (90%).
   - **openai-mini** is weak everywhere — a capability floor, not an interaction.
3. **Robustness ≠ peak.** `deepseek-pro` (model_gap 0/0/0/5 across docling/dots/mineru/
   paddle) and `sonnet-4.6` (1/2/2/2) **never collapse**. The single highest *cell* is
   deepseek-pro on docling (100%), but for an agent that doesn't choose the parser per
   paper, the property that matters is **worst-case across parsers** — where pro and
   sonnet win.

### 5.6 A caution the re-run itself surfaced
The cached re-run gives **sonnet on dots = 85%**, contradicting `FINDINGS.md #3`'s
"sonnet collapses on dots (57%)." That earlier number came from a partial/older run
(the null-crash era), and only DeepSeek's temperature is pinned to 0 — OpenRouter/
Anthropic carry run-to-run variance. **Lesson: single-cell claims need caching +
re-score (now possible) or multi-run averaging.** The *structural* findings (coverage
ceiling, granularity interaction, robustness ordering) are stable across runs and across
the gold fix; exact per-cell recalls carry ±a few points of noise.

---

## 6. Where the numbers landed — the two snapshots side by side

The honest way to read T72 is to hold both views at once.

| | 06-20 view (`FINDINGS.md`) | 06-21 view (`T72-error-analysis.md`) |
|---|---|---|
| Gold | 41 tuples | 40 tuples (dropped `Stability 2.5`) |
| prompt_hash | `bd526972a038` | `9f23e7c683a0` |
| Cost of run | ~€14 cumulative (Stage 1+2) | **€0** (re-scored from cache) |
| Headline framing | model *rankings* (gemini-lite best, flash worst) | *decomposition* (82% hits; misses = 72% model / 28% coverage) |
| What "no 100%" meant | model weakness / parser-fragility | mostly coverage ceiling + gold thinness |
| Best model story | gemini-3.1-flash-lite, 0.80 avg µF1 | robustness winners: deepseek-pro & sonnet (never collapse) |

**Per-parser best (raw, micro-recall, full-5-paper models):** mineru → deepseek-pro 90%
· docling → deepseek-pro 100% / sonnet 98% · dots → deepseek-pro 90% · paddle →
sonnet 95% / deepseek-pro 88%. **Cost/correct spread:** ~€0 (gemini-free) and €0.0006
(deepseek-flash) at the cheap end up to €0.0338 (opus, dropped) at the top — a ~50×
spread, which is the entire point: **the cheap end is competitive.**

**Budget position:** ~€14 / €50 at the end of the 06-20 grid; the ledger later reached
~€24 after an Anthropic top-up to complete the haiku/sonnet cells; the 06-21 re-scoring
itself added **€0**. Comfortably under cap.

---

## 7. Open questions and risks

- **Gold meaning-blindness is uncorrected by design.** Right-number-wrong-catalyst
  (the "40 h = reference catalyst," "1600 h = scale-up cell" class) is invisible to the
  scorer. Fixing it means extending gold tuples to carry catalyst+condition and writing
  a meaning-aware scorer — a task-definition change, deliberately deferred.
- **The locked runtime default is still `deepseek-v4-flash` — the worst overall model.**
  Changing it is a CLAUDE.md-locked decision (user's call). Candidates: `deepseek-v4-pro`
  (safe drop-in, same provider/wire, just `model=deepseek-v4-pro`, never collapses) or
  `gemini-3.1-flash-lite` (best 06-20 average, but points the runtime at a new provider).
- **Precision is structurally understated** wherever models extract real, in-scope
  values the gold omits (thinness on papers 3, 5). The `fp` count is an upper bound on
  model noise, not a measurement of hallucination.
- **Partial data must stay flagged.** sonnet-paddle (2/5) and gemini-free (partial,
  excludes the only ceiling paper) are *not comparable* to full rows and must never be
  quoted as if they were.
- **Coverage is necessary-not-sufficient for small integers.** A standalone "30" can
  match a "30 h" gold by coincidence, so the coverage ceiling is slightly optimistic for
  small-integer tuples (conservative for the distinctive figure values that drive the
  ranking).
- **Single-cell variance.** Only DeepSeek is temperature-pinned; per-cell recalls move
  ±a few points run to run. Structural findings are stable; specific cells are not.

---

## 8. Next-step recommendations

From `T72-error-analysis.md` §6 — what to actually build, grounded in the decomposition.
All bounded, budget-gated, deterministic; **no new agent layer** (planner/critic/router,
LLM-judge, and vector retrieval are all CLAUDE.md anti-patterns).

1. **Parser union for coverage, not a single parser.** Any text parser ∪ a figure-aware
   parser (docling/paddle) is 100% on every paper. Extract over docling/paddle as
   primary; when an expected quantity class is *absent*, fall back to a second parser's
   spans before concluding "not reported." Turns the paper-4 Tafel ceiling from a hard
   miss into a recoverable one. Cost: one cached parse + one extra extraction call *only
   on gap detection*.
2. **Coverage-aware self-verification (the real "second pass").** After pass 1, for each
   measurement *kind* the skill expects but pass 1 didn't return, re-prompt with a
   targeted question restricted to spans carrying that kind's unit cues. Directly attacks
   the `model_gap` bucket (143/200 misses). One cheap call per missing kind, not per
   paper.
3. **Type-reconciliation, not type-strictness.** `wrong_type` is <1%, so the win is
   small — but normalize sibling-class confusions at write time (unit-signature routing
   via `extract.py:units_match`) rather than dropping them.
4. **Attribution capture for trust.** Surface catalyst+condition in the
   human-verification view so the supervisor catches the "40 h = reference catalyst"
   class of error that bare numbers hide. The agent already captures `condition`.
5. **Pick the model on worst-case robustness, not peak cell.** `deepseek-pro` and
   `sonnet-4.6` are the only models that never collapse on any parser; flash and haiku
   each collapse on a *different* one. Since the agent doesn't choose the parser per
   paper, the default should be the robust one — and `deepseek-pro` is a drop-in for the
   current default.

---

## 9. Bottom line

The ground truth is **numerically real but meaning-blind**; its one genuine mislabel is
fixed, and fixing it erased 24 phantom "model failures." The parser ranking and the
failure to reach 100% are **mostly a coverage ceiling** (4 figure-only values on
mineru/dots) plus gold thinness — **not model weakness**. The genuine model signal lives
in the `model_gap` bucket, and that's where a coverage-aware second pass + parser union
pay off. And the original thesis question is answered in the affirmative: **structured
extraction does not need a big model** — the cheap end (deepseek-pro at €0.0017/correct,
free gemini at €0) matches or beats Sonnet/Opus once you account for the parser. Every
paid extraction is now cached, so this entire analysis re-runs for €0.
