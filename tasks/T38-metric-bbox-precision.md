# T38 — Parser metric: bbox precision

**Status:** paused (2026-06-22) · **Group:** evaluation (thesis) · **Priority:** high

> **Paused (2026-06-22):** benchmarking paused pending T73 funding. Metric logic
> currently lives in `experiments/` (`llm_matrix.py` / `ab_extract.py`), not yet
> lifted into a tested module. Resumes with T73.

> **Updated 2026-06-19** — part of the shared T36–T39 comparison. The detailed T49 note
> below already fixes the parser set + Chandra exclusion + coordinate conventions; the
> line about parsers "scoring 0" is superseded by that note (Chandra is *excluded*, not 0).
> See T39 + `report/supervisor-answers-2026-06-19.md` §1a.

## Why
Does each parser tell us WHERE a number came from with enough accuracy to highlight in the viewer?

## Input state
- T35 merged.

## Output state
- File `experiments/bbox_precision.py` computes:
  - For each ground-truth labeled value, find the corresponding bbox in each parser's output (by source_text matching).
  - Compute IoU (intersection over union) between parser-bbox and ground-truth-bbox.
  - Report per-parser: % of labels with IoU > 0.5, mean IoU.
- File `experiments/bbox_precision.csv`.

## Verification
```bash
pixi run python experiments/bbox_precision.py
test -f experiments/bbox_precision.csv
```

## Will touch
- `experiments/bbox_precision.py` (new)
- `experiments/bbox_precision.csv` (generated)

## Will NOT touch
- Anything else.

## Out of scope
- Visual diff against PDF rendering — too brittle.

## Notes / references
- IoU formula: `intersection_area / (area_a + area_b - intersection_area)`.
- Some parsers don't emit bboxes at all (or only at the page level) — those score 0 on this metric. That's important data: low-bbox-precision parsers are worse for the viewer use case.
- **T49 (2026-06-12) — what this metric now measures.** Bboxes on `Evidence` are no
  longer LLM-transcribed; T49 resolves them from each parser's native geometry by
  matching the LLM's `source_text` quote against parser spans (union of matched spans).
  So this metric scores **parser localization**, as intended. Two consequences T38 MUST
  handle:
  - **Coordinate conventions differ per parser** and are stored NATIVE (un-normalized):
    docling uses a BOTTOMLEFT origin in points (bbox dict `l,t,r,b` → stored as
    `x0,y0,x1,y1` with `y0>y1`); mineru/dots/paddle use a TOPLEFT-ish origin in pixels.
    Normalize per-parser by page width/height (and flip docling's y-axis) before computing
    IoU against ground truth, or scores will be meaningless.
  - **Chandra has no geometry** → under the T49 B-scope decision its measurements never
    reach the graph (they route to `errors`), so there are no Chandra bboxes to score.
    Exclude Chandra from this metric explicitly and report it as "no geometry," not IoU 0.
  - Invariant T49 guarantees: every bbox present in the graph is parser-native, so any
    `Evidence` you read here already has a real parser bbox (no fabricated ones to filter).
