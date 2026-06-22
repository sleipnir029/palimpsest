# T82 — Marimo analysis skill / templates for the RDF graph

## Why
The agent can spawn marimo (`open_notebook`) and query the graph (`sparql_query`),
but has **no guidance or scaffold** for turning the extracted RDF into a useful
analysis notebook. The human wants reusable, parameterized analysis of OER metrics
(overpotential distributions, Tafel comparisons, coverage by parser/paper) rather
than hand-writing SPARQL + plotting each time.

## Decision to make FIRST
The skill system is **extraction-shaped** (`SKILL.md` declares `targets:` validated
against `schema/palimpsest.yaml` by the T69 gate). An analysis playbook is a **task**
skill with no `targets:`. Two paths:
- **(A) Templates (recommended, ponytail):** ship 1–2 marimo notebook templates that
  `open_notebook` parameterizes — no skill-system change.
- **(B) Task-skill generalization:** teach the loader/gate to accept non-extraction
  "task" skills (no `targets:`, skip the schema gate) and add `skills/graph-analysis/
  SKILL.md`. More flexible, but it changes a code-enforced invariant — confirm first.

Start with (A); promote to (B) only if discoverability earns it.

## Output state (target)
- `analysis/templates/oer_overview.py` (+ maybe `parser_coverage.py`): a marimo notebook
  that runs a SPARQL SELECT over the store → polars/pandas dataframe → cells with an
  overpotential histogram, a Tafel scatter, and a coverage table — each cell carries
  the provenance columns (paper_hash, parser, page) so the human can verify.
- `open_notebook` gains an optional `template` arg that fills a template with the
  current store path and launches it.
- (Path B only) skill loader accepts task skills; `read_skill`/`check_skill` tolerate
  a `targets:`-less skill; the agent reads it before generating a notebook.

## Verification
- Open a templated notebook over the demo graph; confirm cells render + plots draw.
- A test that template parameterization yields valid, importable marimo Python
  (`python -c "import ast; ast.parse(open(path).read())"` at minimum).
- Spend €0 — no LLM/GPU; pure read of the existing store.

## Will touch
- `src/palimpsest/tools/open_notebook.py`, `analysis/templates/*.py` (new),
  (Path B only) the skill loader + `check_skill` gate.

## Will NOT touch
- The extraction-skill schema gate (unless Path B is deliberately chosen + confirmed).
- The graph store / cost ledger (read-only analysis).
