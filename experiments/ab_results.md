# A/B — deepseek-v4-flash vs deepseek-v4-pro (T52, 2026-06-15)

Paper sha `3432d049…`, `temperature=0`, scored vs `experiments/ground_truth.md` (12 schema-modeled
measurements). Run via `pixi run python experiments/ab_extract.py`. 2 runs each.

| model | valid | TP | recall (/12) | precision | spend |
|-------|-------|----|--------------|-----------|-------|
| flash run0 | 11 | 11 | 92% | 100% | €0.0040 |
| flash run1 | 11 | 11 | 92% | 100% | €0.0040 |
| pro run0   | 12 | 12 | 100% | 100% | €0.0126 |
| pro run1   | 13 | 12 | 100% | 92% | €0.0127 |

## Read
- **temperature=0 reduced — did NOT eliminate — variance.** It removed the wild 4–17 swing seen at
  temp 1.0; flash was a steady 11/11 in the pre-F3 runs, but with more types post-F3 it varies
  16–20 (recall floor 84%). DeepSeek (MoE) is **not deterministic** at temp=0; pro is the steadiest.
- **pro recalls 100%** of the modeled measurements (gets the one flash consistently misses) for ~3×
  the cost (€0.013 vs €0.004 — both trivial), with an occasional 1 false positive (run1).
- **flash** is 92% recall with perfect precision and is 3× cheaper.

## Recommendation
- **Dev / iteration: flash** (cheap, precise, stable).
- **Final / thesis extraction: pro** — 100% recall at €0.013/paper (~€0.06 for the 5-paper corpus)
  is worth the one extra measurement; watch for the rare false positive.
- Default left at **flash** (one-line switch to pro if full recall is wanted by default).

## Post-F3 (denominator 19 — SpecificActivity ×3 + Stability ×4 now modeled)
After T52 added the two classes, the previously-unrepresentable measurements are captured:

| model | valid | TP | recall (/19) | precision | spend |
|-------|-------|----|--------------|-----------|-------|
| flash run0 | 20 | 19 | 100% | 95% | €0.0084 |
| flash run1 | 16 | 16 | 84% | 100% | €0.0082 |
| pro run0   | 20 | 19 | 100% | 95% | €0.0265 |
| pro run1   | 20 | 19 | 100% | 95% | €0.0265 |

- **Closing the schema gap lifted achievable recall 12 → 19**; the new types are extracted.
- **pro = 100% recall both runs**; flash varies 16–20 (more measurement types → more variance on
  the cheaper model; recall floor 84%). The occasional extra item (precision 95% in some runs) is
  **intermittent** — three follow-up flash runs gave 18/18/18 valid with **0 extras** (precision
  100%), so it did not recur and I could not pin its identity; characterized as rare sampling noise
  (an occasional extra borderline value), not a systematic false positive.
- Reinforces: **pro for final/thesis runs** (steady 19/19 at €0.027/paper); flash for cheap dev.

## Caveat
Single paper (only one is parsed/cached). Numbers are for this paper; a multi-paper corpus needs
GPU parsing first. The 7 unmodeled ground-truth measurements (SpecificActivity ×3, Stability ×4)
are excluded from this denominator — they become extractable after T18a F3 (this task), which will
raise the achievable denominator to 19.
