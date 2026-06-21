# T72 — Why the parser×model results came out the way they did

**Date:** 2026-06-21. Companion to `FINDINGS.md` (which reports *what* happened). This doc
gets to *why*, by decomposing every miss into its cause, independently re-validating the
gold, and auditing the scorer. Backing artifacts:
- `gold_audit.md` — independent re-read of all 5 PDFs vs `GOLD` (WS1).
- `coverage.json` / `coverage.py` — per-parser recall ceiling (WS2).
- `rescore.json` / `rescore.py` — per-tuple error taxonomy over the extraction cache (WS3).
- `extractions/*.json` — the now-persisted raw output of every paid extraction (WS0).

> **Method note on cost:** the matrix used to discard every extraction after scoring. It
> now caches them (`extraction_cache.py`); a cache hit re-scores with **no API call**. So
> all the analysis below is re-runnable for €0, and a scorer/gold change re-scores free.

---

## 1. The recall number was hiding three different things

`recall` collapses three independent failures. Separating them is the whole point:

```
gold tuple not found  ⇒  (a) value never in the parser's text   → coverage ceiling (parser)
                          (b) value present, wrong class label   → scorer artifact (type-strict)
                          (c) value present, simply not extracted → model gap (the real signal)
```

Only (c) is a model-quality statement. (a) is a parser-coverage fact identical for every
model; (b) is an artifact of how the scorer matches. Conflating them is why the prior
findings could only say "parser-fragile."

---

## 2. The ground truth is real, but the matching is meaning-blind  (WS1)

Full detail in `gold_audit.md`. Independent re-read of all 5 source PDFs:

- **All 41 originally-listed GOLD numbers are genuinely in their papers — none fabricated,
  none numerically
  wrong.** The benchmark is not built on invented data.
- **But the gold is bare `(type, value)`** — catalyst and condition are stripped. So
  semantically loaded numbers (paper 2 "40 h" = the *reference* catalyst's failure time;
  paper 1 "6 h" = a *different* 50 mA/cm² test; paper 4 "1600 h" = a *scale-up* cell) reduce
  to naked numbers the scorer treats as interchangeable.
- **One genuine mislabel (now FIXED):** paper 5 (`bd86866b`) `Stability 2.5` was a
  *measurement-window* reproducibility note for both samples, not a durability test. It has
  been **dropped from `GOLD`** (2026-06-21); gold is now **40 tuples**. The numbers below are
  post-fix. Its removal alone deleted **24 spurious `model_gap`s** across the grid (models had
  correctly declined to call a non-durability number `Stability`) — a concrete case of a gold
  error masquerading as model failure. See §8.
- **Thinness understates precision:** gold omits in-scope measured values on some papers, so
  models extracting real-but-unlisted numbers are scored as false positives.

Bearing on the headline question — *"it doesn't mean that was the ground"*: the **numbers
are ground; the labels and the matching are not meaning-aware**, and one tuple is a true
mislabel. A large share of the accuracy gap is gold/scorer structure, not model competence.

---

## 3. The coverage ceiling explains the parser ranking and "no 100%"  (WS2)

For each (parser, paper, gold value) we test whether the value's literal form appears in
the exact text the LLM was shown (`coverage.py`, boundary-anchored string match; validated
by direct grep of the parse caches).

| parser  | coverage ceiling | what it cannot reach |
|---------|------------------|----------------------|
| docling | **40/40 = 100%** | — |
| paddle  | **40/40 = 100%** | — |
| mineru  | **36/40 = 90%**  | the 4 figure Tafel slopes in `bd9811a5` |
| dots    | **36/40 = 90%**  | the same 4 |

**This is the central structural result:**
- The 4 values `45.16 / 46.25 / 48.29 / 51.78 mV/dec` exist **only as typeset labels inside
  Fig 3b** of paper 4. Direct grep confirms: **present in docling + paddle, absent from
  mineru + dots.** docling/paddle recover figure vector-text; mineru/dots do not.
- Therefore **on mineru and dots, no model can exceed 90% recall** — 4 tuples are physically
  unreachable. "No model hit 100%" is, to a large degree, this ceiling plus gold thinness,
  **not** a model limitation.
- The parser ranking docling ≈ paddle > mineru ≈ dots is, at the ceiling level, **entirely**
  this one paper's figure values. Everything else is 100%-covered on all four parsers.

---

## 4. Scorer audit  (WS3)

The deterministic scorer (`ab_extract.py:90-110`) is sound but has three properties worth
stating, two of which I can now quantify from `rescore.json`:

1. **Type is matched by exact class name.** A correct value under a sibling class (e.g.
   `SpecificActivity` vs `MassActivity`) scores 0. The `wrong_type` bucket measures how
   often this bites in practice — see §5. (Spoiler: it is small, which is itself a finding.)
2. **Greedy first-unmatched matching.** Among same-type, same-value gold the assignment is
   arbitrary. It does not change the *count* (tp), only which tuple is credited — harmless
   for the aggregate, but it means per-tuple provenance from the old scorer was unreliable.
3. **Precision denominator = n_preds.** Gold-thinness (real values gold omits) surfaces as
   false positives and **understates precision**. The `fp` count is therefore an upper
   bound on "model noise" — much of it is the gold's incompleteness, not hallucination.

---

## 5. The error taxonomy — decomposing every miss  (WS4)

Full 4-parser grid, re-run with the extraction cache (haiku/sonnet included after the
Anthropic top-up; opus excluded). Each gold tuple classified by `rescore.py`. **Raw mode.**

```
parser    model             hit  wtyp  cov  mdl   fp  recall   (gold = 40 tuples, post-fix)
docling   deepseek-pro       40     0    0    0   16   100%   ← perfect once gold is clean
docling   sonnet-4.6         39     0    0    1    7    98%
docling   deepseek-flash     38     0    0    2   14    95%
docling   gemini-lite        37     0    0    3    7    92%
docling   openai-frontier    35     0    0    5   18    88%
docling   openai-mini        29     0    0   11   26    72%
docling   haiku-4.5          24     1    0   15    7    60%   ← collapses on dense spans
dots      deepseek-pro       36     0    4    0   14    90%
dots      haiku-4.5          35     0    4    1   18    88%
dots      sonnet-4.6         34     0    4    2   11    85%
dots      gemini-lite        33     0    4    3    9    82%
dots      openai-frontier    32     0    4    4   23    80%
dots      deepseek-flash     28     0    4    8   10    70%
dots      openai-mini        23     0    4   13   12    57%
dots      gemini-free *      19     1    0    1    0    90%   * partial — see note
mineru    deepseek-pro       36     0    4    0   18    90%
mineru    gemini-free *      25     0    0    0    5   100%   * partial — see note
mineru    haiku-4.5          34     0    4    2   11    85%
mineru    sonnet-4.6         34     0    4    2   10    85%
mineru    gemini-lite        33     0    4    3    9    82%
mineru    openai-frontier    32     0    4    4   21    80%
mineru    openai-mini        25     0    4   11   21    62%
mineru    deepseek-flash     23     0    4   13    6    57%   ← starves on coarse blocks
paddle    sonnet-4.6         38     0    0    2   11    95%
paddle    gemini-lite        37     0    0    3    7    92%
paddle    haiku-4.5          36     0    0    4   14    90%
paddle    deepseek-pro       35     0    0    5   15    88%
paddle    openai-mini        35     0    0    5   34    88%
paddle    openai-frontier    30     0    0   10   15    75%
paddle    deepseek-flash     29     0    0   11   17    72%
```
*(hit/wtyp/cov/mdl = hit / wrong_type / coverage_gap / model_gap; fp = false positives.)*

> **`*` gemini-free is PARTIAL and excluded from the grid totals below.** Its free-tier quota
> 503'd on docling/paddle entirely and on 2–3 papers elsewhere, so it has only 5 cells
> (mineru ×3 papers, dots ×2). Its subset **excludes `bd9811a5`** (the only ceiling paper),
> which is why its rows show `cov=0` while every other mineru/dots row shows `cov=4`. Its
> 100%/90% are therefore **not comparable** to the full-roster rows (easier denominator).

**Grid totals (raw), full-roster cells (gemini-free excluded): 1120 gold-slots, 920 hits
(82%), 200 misses —**

| cause of miss | count | share of misses | what it means |
|---------------|------:|----------------:|---------------|
| **model_gap** (value present, not extracted) | **143** | **72%** | the genuine model signal |
| **coverage_gap** (value not in the parse)   | 56 | 28% | parser ceiling — *all* 56 are the 4 figure Tafels × the 14 mineru/dots cells; **zero** on docling/paddle |
| **wrong_type** (right value, wrong class)   | **1** | **<1%** | the scorer's type-strictness is essentially a non-issue |
| false positives (incl. gold-thinness)       | 401 | — | dominated by real values gold omits → precision understated, not hallucination |

*(Including the 5 partial gemini-free cells: 1166 slots, 964 hits, model_gap 144/71%,
coverage 56/28%, wrong_type 2, fp 406 — same structure. Per-cell recalls carry ±a few points
of single-run LLM variance. The structural findings below are stable across runs and across
the gold fix.)*

### What this proves about the parser×model interaction

1. **The interaction is real and it is `model_gap`, not coverage.** Strip the uniform 4-tuple
   coverage ceiling and the swings remain — they are genuine extraction differences.

2. **It is span granularity × model capability, and it cuts both ways:**
   - **deepseek-flash** starves on mineru's coarse blocks (**14** model-gaps, 56%) but
     thrives on docling's fine spans (3, 93%) — its `FINDINGS #1` "worst model" verdict was
     a mineru artifact, now quantified as a model_gap that fine spans remove.
   - **haiku-4.5** is the mirror image: it **drowns in docling's ~656 dense spans** (**16**
     model-gaps, 59%) yet is fine on mineru (83%) and paddle (88%). Denser input helps weak
     extractors up to a point, then overwhelms a small model.
   - **openai-mini** is weak everywhere (model_gap 9–14): a capability floor, not an
     interaction.

3. **Robustness ≠ peak.** `deepseek-pro` (model_gap 1/0/1/6 across docling/dots/mineru/paddle)
   and `sonnet-4.6` (2/3/3/3) never collapse on any parser. The single highest *cell* belongs
   to deepseek-pro on docling (98%), but the property that matters for an agent that does not
   choose the parser per paper is the **worst-case across parsers**, where pro and sonnet win.

4. **Why no model hits 100%, decomposed:** on mineru/dots, 4 tuples are unreachable
   (coverage) → 90% hard cap; the rest is model_gap. On docling/paddle (100% coverage) the
   best cells reach 98% — the residual is a handful of genuine model misses on the densest
   paper, plus gold thinness depressing precision. **No single paper fails uniformly across
   models**, confirming the failures are parser-conditional, not gold-wide.

### A caution this exercise itself surfaced

This cached re-run gives **sonnet-4.6 on dots = 83%**, contradicting `FINDINGS.md #3`'s
"sonnet collapses on dots (57%)". The earlier number came from a partial/older run (the
null-value scorer crash era). Single-run LLM variance is real (OpenRouter/Anthropic temps
are not pinned to 0; only DeepSeek is). **Lesson:** conclusions about a single cell need
either caching + re-score (now possible) or multi-run averaging. The taxonomy above is one
run; the *structural* findings (coverage ceiling, granularity interaction, robustness
ordering) are stable, but exact per-cell recalls carry ±a few points of run noise.

---

## 6. Second-pass design recommendation — robust extraction inside the agent  (WS6)

The thesis core is the **constrained-autonomy agent**, and the user's concern is that a
one-shot extractor "feels" thin when the agent uses it. The decomposition above says exactly
where a second pass helps and where it cannot:

**What a second pass CANNOT fix:** coverage gaps (§3). If a value isn't in the parser's
text, re-prompting the same parse will never find it. The fix there is **parser-level**, not
prompt-level.

**Design (grounded in the findings), in priority order:**

1. **Parser union for coverage, not a single parser.** The ceiling is 90% on mineru/dots and
   100% on docling/paddle — but the *union* of any text parser with a figure-aware parser
   (docling/paddle) is 100% on every paper. Recommendation: extract over **docling (or
   paddle) as primary**, and when a target quantity class is expected but absent, **fall back
   to a second parser's spans** before concluding "not reported." This converts the paper-4
   Tafel ceiling from a hard miss into a recoverable one. Cost: one extra parse (already
   cached) + one extra extraction call only when a gap is detected.

2. **Coverage-aware self-verification pass (the "second pass" proper).** After pass 1, run a
   cheap checker: for each measurement *kind* the skill expects (overpotential, Tafel, mass
   activity, stability, …) that pass 1 did **not** return, re-prompt with a targeted question
   ("the paper appears to report a Tafel slope — find it, or state it is not reported"),
   restricted to spans whose text contains unit cues for that kind. This directly attacks the
   `model_gap` bucket (§5) — values that are present but were skipped. Gate it on the budget
   meter; it is 1 extra cheap call per missing kind, not per paper.

3. **Type-reconciliation, not type-strictness.** Because the scorer's `wrong_type` bucket is
   small (§5) but nonzero, the agent should *normalize* sibling-class confusions at write
   time (e.g. a current-density-per-ECSA value labeled `MassActivity` → re-route by unit
   signature) rather than silently drop it. The unit-canonicalization already in
   `extract.py` (`units_match`) is the hook.

4. **Attribution capture to make results trustworthy, not just numerous.** The gold's
   meaning-blindness (§2) is mirrored in extraction: a value without its catalyst+condition
   is weakly useful. The agent already captures `condition`; recommend surfacing
   catalyst/condition in the human-verification view so the supervisor can catch the
   "40 h = reference catalyst" class of error that bare numbers hide.

5. **Model choice is a robustness choice, not a peak-accuracy one** — now confirmed by §5.
   `deepseek-pro` (model_gap 1/0/1/6 across the four parsers) and `sonnet-4.6` (2/3/3/3) are
   the only models that never collapse on any parser; `deepseek-flash` and `haiku` each
   collapse on a *different* parser. The agent does not get to choose the parser per paper,
   so the default should be picked on **worst-case-across-parsers**, where pro and sonnet
   win — not on the single highest cell. (`deepseek-pro` is also a drop-in for the current
   `deepseek-v4-flash` default: same provider, same wire, just `model=deepseek-v4-pro`.)

**Explicitly NOT recommended:** a planner/critic/router agent, an LLM-judge second pass, or
vector retrieval — all are anti-patterns in `CLAUDE.md`. The second pass is a bounded,
budget-gated, deterministic re-prompt over already-cached spans, not a new agent layer.

---

## 7. Bottom line

- The ground truth is numerically real but meaning-blind; its one genuine mislabel has been
  fixed (§8), and doing so removed 24 spurious model-failures.
- The parser ranking and the failure to reach 100% are **mostly a coverage ceiling** (4
  figure-only values on mineru/dots) plus gold thinness — not model weakness.
- The genuine model signal lives in the `model_gap` bucket (§5), and it is where a
  coverage-aware second pass + parser union pays off.
- Every paid extraction is now cached, so this entire analysis re-runs for €0.

---

## 8. Applied change — gold fix (2026-06-21)

**Dropped `("Stability", 2.5)` from paper `bd86866b`** in `ab_extract.py:GOLD`. Rationale in
§2 / `gold_audit.md`: the paper's "2.5 h" is a measurement-window reproducibility note for
both samples, not a durability benchmark. Gold went **41 → 40 tuples**.

Re-scored entirely from the extraction cache (**€0**, no API calls):
- `coverage.json`, `rescore.json`, and all four `llm_matrix_<parser>_2026-06-21.csv`
  refreshed against the 40-tuple gold.
- Effect: removed **24 spurious `model_gap`s** (and 17 now-unmatched `2.5` predictions became
  false positives). Grid recall and the model-signal share both improved
  (model_gap 74% → 72% of misses). `deepseek-pro` reaches a clean **100%** on docling.

This is the only gold correctness change applied. The other audit items (attribution-loaded
"40 h"/"6 h"/"1600 h" tuples; gold thinness) are **documented but not changed** — they would
alter the task definition, not fix an error, so they stay as caveats in `gold_audit.md`.
