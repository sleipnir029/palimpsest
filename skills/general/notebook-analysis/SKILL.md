---
name: notebook-analysis
description: Build an interactive marimo notebook that queries the extracted RDF graph and visualizes OER metrics (overpotential distribution, Tafel comparison, parser coverage), with provenance carried into every cell. Use when the researcher wants to explore the graph interactively.
when_to_use: user asks to analyze, explore, plot, or visualize the extracted graph interactively
version: 1.0.0
kind: task
reads:
  - Overpotential
  - TafelSlope
  - Stability
  - Evidence
  - Paper
uses:
  - sparql_query
  - write_file
  - open_notebook
---

# Notebook analysis playbook

Build a **marimo** notebook over the extracted graph. Never auto-run it — write
it with `write_file` into `workspace/notebooks/`, then spawn it with
`open_notebook` so the human drives it.

## Discipline
- Start from `references/notebook_template.py`; change only the SPARQL query and
  the store path. Keep it minimal — one figure per question.
- Query the store directly inside the notebook via `palimpsest.store.RDFStore`.
  Use `sparql_query` first to preview a query before baking it in.
- **Provenance in every cell:** every row you plot must keep its `paper` (sha256),
  `parser`, and `page` columns so the human can trace any point back to the PDF.
  A chart without provenance is not acceptable.
- Charts use `plotly.graph_objects` (NOT `plotly.express`, which needs pandas).
  Feed it plain Python lists built from the SPARQL rows — no dataframe library.
- Do not fabricate or fuse: an RDE η@10 and a PEMWE cell voltage are different
  quantities; never plot them on one axis. See the domain skill's "common traps".

## Suggested cells
1. Imports + store path + the SPARQL SELECT (value, unit, paper, parser, page).
2. Overpotential histogram (`go.Histogram`).
3. Tafel-vs-overpotential scatter (`go.Scatter`, mode="markers").
4. A provenance table (`go.Table`) listing paper/parser/page per point.
