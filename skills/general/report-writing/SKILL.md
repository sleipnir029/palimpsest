---
name: report-writing
description: Generate a self-contained HTML report from the extracted RDF graph — SPARQL-backed figures (plotly), a provenance table, and the domain caveats — for sharing or the thesis. Use when the researcher wants a shareable summary rather than an interactive notebook.
when_to_use: user asks for a report, summary, or shareable export of the extracted graph
version: 1.0.0
kind: task
reads:
  - Overpotential
  - TafelSlope
  - MassActivity
  - Stability
  - Evidence
  - Paper
uses:
  - sparql_query
  - write_file
---

# Report-writing playbook

Produce a **self-contained HTML** report into `workspace/reports/`. Write it with
`write_file`; do not spawn anything.

## Discipline
- Start from `references/report_template.py`; change only the SPARQL queries and
  the prose. Each figure is `plotly.graph_objects` embedded via `fig.to_html(
  full_html=False, include_plotlyjs="cdn")` — no kaleido, no static images.
  The reference query is already schema-correct and runs as-is against a
  populated store.
- `STORE_PATH` and `OUT` are **relative to the repo root**; run from there, or
  `RDFStore("store")` opens an empty store and the report comes out empty (no
  error).
- **Every figure carries a provenance table** (paper sha256, parser, page) for
  the points it shows. A number without provenance does not go in the report.
- Pull the caveats from the domain skill's "common traps": never fuse RDE and
  PEMWE stability; always state iR-correction status and electrolyte.
- Do not fabricate. If the graph lacks a metric, say so — do not invent it.
