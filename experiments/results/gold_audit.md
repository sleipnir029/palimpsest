# T72 — Ground-truth audit: is the "ground truth" actually ground?

**Date:** 2026-06-21 · **Method:** independent re-read of all 5 source PDFs (papers/*.pdf),
each by a separate reader, extracting OER measurements from scratch *and* rendering a
sourced verdict on every `ab_extract.GOLD` tuple. €0 (no API spend — direct PDF reads).

## Headline

**All 41 GOLD numbers are genuinely present in their papers. None are fabricated, and none
are numerically wrong** (within the scorer's 1% tolerance). The benchmark is not built on
invented data.

**But the gold/scorer design systematically depresses measured scores in ways that are not
model failures.** Four structural issues, in decreasing severity:

| # | Issue | Where | Effect on scores |
|---|-------|-------|------------------|
| 1 | **Figure-only values** — present only as typeset labels inside a figure, absent from all body text | paper 4 (`bd9811a5`): 4 Tafel slopes | Hard per-parser **coverage ceiling**: text parsers (mineru/dots/paddle) cannot reach them; only docling can. Caps recall for *every* model on those parsers. Main driver of "no model hits 100%". |
| 2 | **Meaning-blind tuples** — GOLD is bare `(type, value)`; catalyst + condition stripped | all papers | Scorer matches naked numbers, so a value can match for the wrong catalyst/condition. Inflates apparent correctness in some cells, and makes "right number, wrong meaning" invisible. |
| 3 | **One genuine mislabel** | paper 5 (`bd86866b`): `Stability 2.5` | A measurement-window note treated as a durability benchmark — an over-claim that should be removed/relabeled. |
| 4 | **Thinness** — gold omits in-scope measured values | papers 3, 5 especially | Models that extract real-but-unlisted numbers are scored as false positives → **precision is understated**. |

## Per-paper verdicts

### Paper 1 — `3432d049` · Ir-Co₃O₄ · Nat. Commun. 2022 · 19 tuples
- **All 19 CONFIRMED**, all stated in main-text prose (pages 5–6), corroborated by Fig 3.
  Overpotentials 236/298/412/511, Tafel 52.6/75.8/109.8/131.3, mass activity 3343.37/65.35,
  TOF 1.665/0.0237, specific activity 0.098/0.035/0.01, stability 30/15/9/6 — all verbatim.
- **Caveat:** the four "stability" hours are not one comparable series — 30/15/9 are the
  10 mA/cm² chronopotentiometry (Fig 3g); **6 h is a *different* 50 mA/cm² test**. Bare
  numbers hide this.
- This is the only paper whose gold was originally built by **human PDF reading** — and it
  is the cleanest. Worth noting for the methodology section.

### Paper 2 — `c9a68107` · IrO₂@TaB₂ · Nat. Commun. 2023 · 7 tuples
- **All 7 CONFIRMED**, all TEXT-sourced (pages 4–5), exact.
- **Semantic caveat:** `Stability 120` is "**more than** 120 h" for the test catalyst;
  `Stability 40` is the **failure time of the *unsupported* reference IrO₂**, not a
  durability achievement. Numbers right, meaning loaded.

### Paper 3 — `c63193979` · Ir/TiOₓ@Ti · Nat. Commun. 2025 · 4 tuples
- **All 4 CONFIRMED.** Mass activity 192/81 A/g (1.53 V), stability 1700/40 h.
- **`Stability 40` again belongs to the unsupported control (Ir NPs)**, not the headline
  catalyst (which does 1700 h). Attribution stripped.
- **Thin by paper design:** this paper reports **no measured Tafel slope** and **no prose
  overpotential @ 10 mA/cm²** (only a 260 mV figure annotation). Its richest in-prose
  numbers (PEMWE: 1.88 V @ 3 A/cm²; degradation 22/52/27/460 µV/h; η_kin 294/324 mV) are
  PEMWE-cell metrics — partly out of the 3-electrode OER scope, but real and omitted.

### Paper 4 — `bd9811a5` · RuₓIrOₓ · Nat. Nanotechnol. 2025 · 8 tuples  ⚠️ key paper
- Overpotential 240: **CONFIRMED but "~240" and COLLECTIVE** (stated once for all four
  catalysts; no per-catalyst value exists).
- Tafel 45.16 / 46.25 / 48.29 / 51.78: **CONFIRMED as FIGURE-ONLY** (typeset labels in
  Fig 3b). They appear **nowhere in body text, methods, or tables** — verified by full-text
  search. They are the authors' own printed fit values (so the 2-decimal precision is
  legitimate), but: (a) a text-only parse can never recover them; (b) the figure does not
  bind each slope to a specific catalyst, so any per-catalyst attribution is an inference.
- Stability 1500 / 1600 / 200: **all CONFIRMED but three different catalysts/cells** —
  1500 h = Ru₆IrOₓ lab cell (2 A/cm²); **1600 h = Ru₆IrOₓ *scale-up* De Nora cell** (50 A,
  25 cm², 60 °C); 200 h = Ru₂₄IrOₓ. 1500 vs 1600 are trivially conflatable without context.
- **This paper alone explains most of the parser-coverage story.** Its 4 figure Tafels are
  the reachable-only-by-docling values that cap mineru/dots/paddle recall.

### Paper 5 — `bd86866b` · amorphous IrOₓ vs rutile IrO₂ · Nat. Catal. 2024 · 3 tuples
- Overpotential 210 / 330: **CONFIRMED** (page 765, @ 0.5 mA/cm²_geo). Note IrOₓ is written
  "**−210 mV**" (signed) — magnitude matches, but a sign-aware schema would differ.
- `Stability 2.5`: **the string "2.5 h" is real but the label is wrong.** The sentence says
  "the redox features and catalytic activity of **both samples** are relatively stable for
  20 cycles and **2.5 h of operation**" — a *measurement-window reproducibility* note, not a
  durability/endurance test. The paper's actual durability statement is "~2 orders of
  magnitude lower lifetime at 1 mA/cm²_geo" (cited). **Recommend removing or relabeling.**
- Thin by paper design: a mechanistic spectro-electrochemistry study — **no Tafel, no mass
  activity, no long durability test** exist to extract.

## GOLD changes

A GOLD edit re-defines every prior score, so each is re-scored from the extraction cache
(free, no API).

1. **APPLIED (2026-06-21) — `bd86866b`: dropped `("Stability", 2.5)`.** Not a durability
   measurement; the one clear correctness fix. Gold is now 40 tuples (that paper → 2 tuples).
   Re-scored from cache: removed 24 spurious `model_gap`s across the grid (models had
   correctly declined to call a non-durability number `Stability`). See
   `T72-error-analysis.md` §8. The items below remain **proposed, not applied:**
2. **Annotate, don't change, the attribution-loaded tuples** (`c9a68107`/`c63193979` "40 h" =
   reference catalyst; `3432d049` "6 h" = 50 mA/cm²; `bd9811a5` 1500/1600 = different cells).
   These numbers are correct; the fix is to *record* catalyst+condition so the meaning-blind
   matching is at least documented. Consider extending GOLD tuples to carry a catalyst label
   for a future, meaning-aware scorer.
3. **Mark `bd9811a5`'s 4 Tafel slopes as `figure-only`** in the gold so the coverage ceiling
   is explicit (it already is, in `ab_extract.py:50-58`, but per-tuple flagging lets the
   re-scorer separate "ceiling" from "model gap" automatically).
4. **Leave the thinness as-is for the benchmark** (adding PEMWE/out-of-scope metrics would
   change the task), but note it: precision is understated wherever models extract real,
   in-paper, in-scope values that gold omits.

## What this means for the headline question

> "the ground truth we considered as ground — it doesn't mean that was the ground."

Correct instinct, partially borne out: the **numbers are ground**, but the **labels and the
matching are not meaning-aware**, and **one tuple (paper 5 2.5 h) is a genuine mislabel**.
Most importantly, a large part of the measured accuracy gap — especially the parser ranking
and the failure to reach 100% — is **explained by gold structure (figure-only values,
thinness), not by model competence.** The coverage decomposition (`coverage.py`) quantifies
how much.

---

## Gold version bump (2026-06-21, T74): 40 → 47 tuples

T74's gold-thinness audit (`gold_thinness.py` + `gold_verification_t74.md`) found
real measurements the gold under-scoped — full-cell PEMWE metrics the three-electrode
OER gold never listed, which the models extracted correctly but scored as false
positives. Added after parser-text verification (PDF-confirmed for the single-parser
ones):

| paper | added tuples | evidence |
|---|---|---|
| c9a68107 (s41467-023-40912-8) | PEMWECellVoltage 1.67, 1.83, 2.0 | Fig 5c labels 1.67 V @1 A/cm², 1.83 V @2 A/cm² (PDF p7); 2.0 V @3.06 A/cm² (text) |
| bd9811a5 (s41565-025-02030-y) | PEMWECellVoltage 1.939, 1.986, 2.0 | "voltage rose from 1.939 V to 2.000 V in first 500 h … 1.986 V at 1,600 h" (docling+paddle identical) |
| c63193979 (s41467-025-63541-9) | Stability 400 | "operational stability … over 400 h at both 1 A/cm² and 2 A/cm²" (docling+dots) |

**Deferred (not added):** DegradationRate values (22/52/2.3–2.8 µV/h). The
extractions emitted them in µV/h under an mV/h label without converting (1000× off).
NOTE (post C3-review): DegradationRate is **not** magnitude-guarded by C3 — a µV/h-as-mV/h
blunder is indistinguishable from a real high accelerated-stress rate, and a correctly
converted value (0.022 mV/h) is blocked upstream by the mis-citation guard anyway. Clean
DegradationRate extraction needs unit re-derivation from the cited span (deferred), not a
magnitude bound. Other ≥3-agreement candidates were rejected as artifacts/duplicates/
wrong-quantity — see `gold_verification_t74.md`.

**Impact:** denominators grew, so recall numbers in the T72 FINDINGS/report (built on
the 40-tuple gold) differ from re-scores on the 47-tuple gold. The stamped T72 CSV
snapshots remain the frozen 40-tuple record; T74 results use 47. The change only
strengthens the T74 headline (model-union docling 100% vs sonnet single-shot 91%).
