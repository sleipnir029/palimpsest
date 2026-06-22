# T37 — Parser metric: table-cell F1

**Status:** paused (2026-06-22) · **Group:** evaluation (thesis) · **Priority:** high

> **Paused (2026-06-22):** benchmarking paused pending T73 funding. Metric logic
> currently lives in `experiments/` (`llm_matrix.py` / `ab_extract.py`), not yet
> lifted into a tested module. Resumes with T73.

> **Updated 2026-06-19** — scoreable parser set is **{docling, mineru, dots, paddle}**
> (Chandra not parsed on this corpus — T34). Part of the shared T36–T39 parser
> comparison (ceiling = ground truth, T35). See T39 + `report/supervisor-answers-2026-06-19.md` §1a.

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
