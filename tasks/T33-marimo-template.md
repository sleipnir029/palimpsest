# T33 — Marimo template with SPARQL cell

## Why
Standard template the agent uses when generating analysis notebooks. SQL cell reads from RDFStore, plot cell visualizes.

## Input state
- T32 merged. open_notebook tool works.
- T24 merged. RDFStore exists.

## Output state
- File `notebooks/_template_default.py` exists with cells:
  1. Imports (marimo, palimpsest.store, plotly).
  2. SQL cell using marimo's SQL feature: query overpotentials by paper from the RDFStore. (Marimo's SQL feature can wrap a SPARQL query inside a Python cell that calls `RDFStore.sparql(...)` — write it as Python, marimo handles the reactivity.)
  3. Plot cell: bar chart of overpotentials.
  4. Markdown cell: short instructions on how to modify.
- File `notebooks/_template_parser_comparison.py` exists for the week 5 parser comparison work. Cells include: load CSV of parser results, side-by-side bar plots per metric.
- Each template is < 100 LOC.

## Verification
```bash
# Smoke: marimo can open the templates without error
marimo edit notebooks/_template_default.py --headless --port 0 &
sleep 5
kill %1
```
No error during the 5 seconds the editor is up.

## Will touch
- `notebooks/_template_default.py` (new)
- `notebooks/_template_parser_comparison.py` (new)

## Will NOT touch
- store.py.
- open_notebook.py (T32 stable).

## Out of scope
- Auto-running notebooks (never).
- More than 2 templates in MVP.

## Notes / references
- Marimo notebooks are pure Python. Each `@app.cell` is a cell.
- SQL feature: https://docs.marimo.io/api/sql/
- Use Plotly Express for plots (already importable; if not, add `plotly` to pixi.toml).
