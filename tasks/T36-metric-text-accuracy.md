# T36 — Parser metric: text accuracy

**Status:** paused (2026-06-22) · **Group:** evaluation (thesis) · **Priority:** high

> **Paused (2026-06-22):** benchmarking paused pending T73 funding. Metric logic
> currently lives in `experiments/` (`llm_matrix.py` / `ab_extract.py`), not yet
> lifted into a tested module. Resumes with T73.

> **Updated 2026-06-19** — scoreable parser set is **{docling, mineru, dots, paddle}**
> (Chandra was never parsed on this corpus — timed out, dropped at T34). Metric +
> baseline scheme is shared across T36–T39: ceiling = human ground truth (T35); this is
> the transcription-fidelity axis. See T39 and `report/supervisor-answers-2026-06-19.md` §1a.

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
- No fixed expected ranking — the comparison *is* the result. (Earlier drafts guessed a
  Chandra/olmOCR ranking; those aren't in the parsed set, so ignore that guess.)
