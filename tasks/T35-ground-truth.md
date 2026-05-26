# T35 — Hand-label 5-paper ground truth

## Why
You can't measure parser quality without ground truth. Pick 5 papers from the corpus and manually verify expected slot values.

## Input state
- T34 merged. All 25 papers parsed.

## Output state
- Directory `tests/ground_truth/` contains 5 JSON files, one per paper:
  - `<sha256>.json` with fields:
    ```json
    {
      "sha256": "...",
      "filename": "...",
      "doi": "...",
      "labels": {
        "overpotential_at_10mAcm2": [{"value": 236, "unit": "mV", "page": 3, "bbox": [...], "source_text": "η = 236 mV at 10 mA cm−2"}],
        "tafel_slope": [...],
        "mass_activity": [...],
        ...
      },
      "labeled_by": "rahat",
      "labeled_at": "2026-..."
    }
    ```
  - At least 10 labeled slots per paper.
- A README in `tests/ground_truth/README.md` describing the labeling protocol (what counts as a valid label, how to handle ambiguous values, etc.).

## Verification
```bash
pixi run python -c "
from pathlib import Path
import json
files = list(Path('tests/ground_truth').glob('*.json'))
assert len(files) >= 5, f'expected 5 ground-truth files, got {len(files)}'
for f in files:
    d = json.loads(f.read_text())
    assert len(d['labels']) >= 10, f'{f.name}: only {len(d[\"labels\"])} labels'
print(f'{len(files)} ground-truth files, all with ≥10 labels')
"
```

## Will touch
- `tests/ground_truth/<sha>.json` × 5 (new)
- `tests/ground_truth/README.md` (new)

## Will NOT touch
- src/.

## Out of scope
- Automated ground truth → not feasible.
- Labeling more than 5 papers → diminishing returns for a 10-credit thesis.

## Notes / references
- This is the most tedious task in the project. Block out 4 hours. Use a printed copy of each paper. Coffee.
- Pick papers with diverse characteristics: one with dense tables, one with lots of equations, one with low-quality scans, etc.
- For each slot, record the EXACT bbox by reading the PDF in a viewer. This is the gold standard you'll evaluate parsers against.
- The bboxes don't have to be pixel-perfect — within a few points is fine. Parser scores will be IoU @ 0.5, not pixel-exact.
