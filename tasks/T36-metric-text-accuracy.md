# T36 — Parser metric: text accuracy

## Why
First parser-comparison metric: how well does each parser reproduce the literal text of the paper?

## Input state
- T35 merged. Ground truth exists.

## Output state
- File `experiments/text_accuracy.py` computes:
  - For each of the 5 ground-truth papers, for each parser, compute Levenshtein-based similarity between parser-extracted text and the ground-truth source_text snippets.
  - Aggregate: per-parser mean similarity, plus per-slot-type breakdown.
- File `experiments/text_accuracy.csv` with columns: `parser, paper_sha, n_snippets, mean_similarity, median_similarity`.

## Verification
```bash
pixi run python experiments/text_accuracy.py
test -f experiments/text_accuracy.csv && head experiments/text_accuracy.csv
```

## Will touch
- `experiments/text_accuracy.py` (new)
- `experiments/text_accuracy.csv` (generated)

## Will NOT touch
- src/.

## Out of scope
- Other metrics → T37-T39.

## Notes / references
- Use `rapidfuzz` library (add to pixi.toml if needed) for fast Levenshtein.
- Expected ranking, roughly: Chandra 2 ≥ olmOCR 2 > MinerU 2.5 ≥ docling. Don't be alarmed if numbers differ — that's data for the thesis.
