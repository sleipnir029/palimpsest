# T40 — SPARQL queries for thesis chapters

## Why
Demonstrate the value of the triple store. Each query is a thesis figure or table.

## Input state
- All 25 papers extracted into the graph (run T22 pipeline on the corpus after T39 or during).

## Output state
- Directory `queries/` contains:
  - `q01_overpotentials_by_catalyst_family.rq` — group catalysts by support (TiO2, TaB2, ATO, none) and average η@10 mA/cm².
  - `q02_tafel_vs_electrolyte.rq` — Tafel slope distribution by electrolyte (0.1 M HClO4 vs 0.5 M H2SO4).
  - `q03_mass_activity_distribution.rq` — A/g_Ir at 1.53 V_RHE across all papers.
  - `q04_stability_hours_vs_ir_loading.rq` — stability hours vs Ir loading, for PEMWE-cell measurements.
  - `q05_mechanism_distribution.rq` — fraction of papers proposing LOM vs AEM vs other.
- File `experiments/run_queries.py` — runs each query, writes results to `experiments/queries/<name>.csv`.

## Verification
```bash
pixi run python experiments/run_queries.py
ls experiments/queries/*.csv
# Each CSV has ≥1 row.
```

## Will touch
- `queries/*.rq` × 5 (new)
- `experiments/run_queries.py` (new)
- `experiments/queries/*.csv` (generated)

## Will NOT touch
- store.py.

## Out of scope
- Plots → T41.

## Notes / references
- SPARQL 1.1 docs: https://www.w3.org/TR/sparql11-query/
- Prefixes: declare `palim`, `qudt`, `emmo`, `prov` at the top of each query.
- Some queries will return empty if the corpus doesn't have those slots well-extracted — that's also data. Report honestly in the thesis.
