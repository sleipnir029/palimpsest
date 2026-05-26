# T38 — Parser metric: bbox precision

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
