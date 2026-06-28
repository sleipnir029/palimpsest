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

Build a **marimo** notebook over the extracted graph. Never auto-run it. See
`[[marimo-pairing]]` for the create/edit/open lifecycle and path rules; this
skill covers the OER-specific query and figures.

## Discipline
- Build the notebook source yourself and pass it to `open_notebook(name=...,
  content=...)` — it writes into `<workspace>/notebooks/<name>.py` for you and
  spawns the editor. Do **not** `read_file` a template or `write_file` the
  notebook to a bare relative path (it resolves outside the workspace and is
  refused). Keep it minimal — one figure per question.
- Query the store directly inside the notebook via `palimpsest.store.RDFStore`.
  Use `sparql_query` first to preview a query before baking it in. The `default`
  template (`open_notebook(template="default")`) ships a schema-correct query that
  returns rows as-is against a populated store — a working baseline, not a
  placeholder.
- Open the store with `RDFStore("store")` exactly as the `default` template does
  — `open_notebook` spawns marimo at the repo root, so `"store"` resolves to the
  on-disk graph (you don't control or need to set the cwd). If the store is
  empty/absent every cell renders blank with no error, so guard it
  (`try/except`, show "run `python -m palimpsest demo <pdf>`") like that template.
- Carry provenance (`paper` sha256, `parser`, `page`) on every plotted row so a
  point traces back to its PDF — see `[[marimo-pairing]]` for the general rule.
- Do not fabricate or fuse: an RDE η@10 and a PEMWE cell voltage are different
  quantities; never plot them on one axis. See the domain skill's "common traps".

## Suggested cells
1. Imports + store path + the SPARQL SELECT (value, unit, paper, parser, page).
2. Overpotential histogram (`go.Histogram`).
3. Tafel-vs-overpotential scatter (`go.Scatter`, mode="markers").
4. A provenance table (`go.Table`) listing paper/parser/page per point.
