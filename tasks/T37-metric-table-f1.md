# T37 — Parser metric: table-cell F1

## Why
OER papers have lots of tables. How well does each parser extract them?

## Input state
- T35 merged.

## Output state
- File `experiments/table_f1.py` computes per-parser table-cell F1:
  - For each paper, identify all tables in the ground truth.
  - For each parser's output, match its extracted tables to ground-truth tables (by overlap or order).
  - Compute precision, recall, F1 of cell-level matches.
- File `experiments/table_f1.csv` with per-parser per-paper F1 scores.

## Verification
```bash
pixi run python experiments/table_f1.py
test -f experiments/table_f1.csv
```

## Will touch
- `experiments/table_f1.py` (new)
- `experiments/table_f1.csv` (generated)

## Will NOT touch
- Ground truth (T35 stable).

## Out of scope
- Other metrics → T38, T39.

## Notes / references
- Cell match: identical or similar (Levenshtein > 0.8) string at the same row/col index.
- Don't worry about merged cells, complex headers — keep it simple. The point is relative comparison, not absolute correctness.
