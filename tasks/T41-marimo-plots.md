# T41 — Plots in marimo notebooks for thesis

## Why
Visualize results. The thesis chapters reference these figures.

## Input state
- T39 (downstream accuracy CSV) and T40 (SPARQL queries CSVs) merged.

## Output state
- Directory `notebooks/thesis/` contains:
  - `01_parser_comparison.py` — 4 subplot bar chart: text accuracy, table F1, bbox precision, downstream accuracy, one bar per parser. Saves PNG.
  - `02_overpotentials_by_family.py` — bar chart of mean η@10 mA/cm² by catalyst family, error bars = std. Saves PNG.
  - `03_tafel_vs_electrolyte.py` — box plots. Saves PNG.
  - `04_stability_landscape.py` — scatter of stability hours vs Ir loading, colored by paper year. Saves PNG.
- Each notebook reads from `experiments/*.csv` or `experiments/queries/*.csv`. No live RDF queries (results are pre-computed).
- Each notebook is < 80 LOC.
- PNGs in `thesis/figures/` (create dir; each PNG ≥ 300 dpi).

## Verification
```bash
# Manual:
marimo edit notebooks/thesis/01_parser_comparison.py --headless --port 0
# Check the figure renders.
ls thesis/figures/*.png
# All 4 expected files present.
```

## Will touch
- `notebooks/thesis/*.py` × 4 (new)
- `thesis/figures/*.png` × 4 (new, regenerated from notebooks)

## Will NOT touch
- experiments/*.csv (T36-T40 stable).

## Out of scope
- Interactive plots in the thesis (it's a PDF document).

## Notes / references
- Use matplotlib (publication quality) over plotly (interactive). PNG exports for the PDF.
- 300 dpi minimum, label all axes with units, no chartjunk.
