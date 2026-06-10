# T46b — reconcile store↔schema so the stored graph passes its own SHACL (C4)

## Why
After T46 (C1), the store writes Conditions, but the **stored graph still does not match
the schema it validates against** — the review's C4 gap. SHACL runs only on the *pre-insert*
JSON-LD rendering (`validation.py::_to_jsonld`), which has a different shape than what
`store.py` persists, so **SHACL currently guarantees nothing about the actual graph**.

Concretely, the closed **concrete measurement shapes** (Overpotential, TafelSlope, etc.;
e.g. `sh:targetClass emmo:…1cd1d777`, `sh:closed true` — note `palimpsest:Measurement`
*itself* is `sh:closed false`, so grep the subclass shape, not the base) allow exactly:
`palimpsest:value`, `palimpsest:unitLabel`, `palimpsest:condition → Condition`,
`prov:hadPrimarySource → prov:Entity` (rdf:type is `sh:ignoredProperties`). But the store
emits `prov:wasDerivedFrom → Paper` and `prov:wasGeneratedBy → activity`, and never
materialises an `Evidence` node. This task makes the persisted measurement subgraph
conform to the shipped shapes.

## Input state
- **T46 (C1) merged** — `Condition`/`Electrolyte` nodes are written (`store.py::_add_condition`).
- `validation.py::_to_jsonld(instance)` exists and produces the exact JSON-LD that SHACL
  validates (reusable — see Notes).
- Closed shapes in `schema/generated/shacl.ttl`: `Measurement` (value, unitLabel, condition,
  prov:hadPrimarySource); `prov:Entity`/Evidence (palimpsest:paper minCount 1, page, bboxX0/Y0/X1/Y1,
  parserName, sourceText); `ScholarlyArticle`/Paper (sha256 minCount 1, name, identifier, author);
  `Condition`; `Electrolyte`. All `sh:closed true` with `sh:ignoredProperties ( rdf:type )`.

## Output state
- `store.py::insert_extraction` emits the **schema-shaped** measurement subgraph:
  - measurement → `palimpsest:value`, `palimpsest:unitLabel`, `palimpsest:condition` → Condition
    (from T46), `prov:hadPrimarySource` → **Evidence node**.
  - **Evidence node** (typed `prov:Entity`): `palimpsest:paper` → Paper, `palimpsest:page`,
    `palimpsest:bboxX0/Y0/X1/Y1`, `palimpsest:parserName`, `palimpsest:sourceText`.
  - Paper node unchanged (`schema:ScholarlyArticle`: sha256, identifier, name).
  - **Remove** `prov:wasDerivedFrom` (measurement→Paper), `prov:wasGeneratedBy` (measurement→activity),
    `prov:used`, and the activity blank node from the *data* graph.
- Run-provenance (`run_id`, `parse_run_id`) handled per the DECIDE block below — it has **no
  SHACL-legal home** on the closed measurement/Evidence nodes, so it must move deliberately.
- **Acceptance bar — validated-form == stored-form:** a new test serialises the inserted
  measurement subgraph and runs `pyshacl.validate(..., shacl_graph=shacl.ttl)` → `conforms == True`.
  (Reuse `validation._shapes()`.) **SHACL conformance is necessary but NOT sufficient:**
  `prov:hadPrimarySource` has `sh:maxCount 1` but **no `sh:minCount`** on any measurement shape,
  so a measurement with no Evidence still passes SHACL. `test_refuses_without_evidence`
  (`tests/test_store.py`) must therefore **survive the rewrite unchanged** — it, not SHACL, enforces
  the provenance non-negotiable.
- Existing `tests/test_store.py` updated: the triple-count, the `prov:wasDerivedFrom`/`wasGeneratedBy`
  assumptions, and `test_two_run_ids_distinct_predicates` change shape — update them deliberately
  to the new model, with documentation, not by bandaiding.

## DECIDE before coding — where do `run_id` / `parse_run_id` live?
T24 deliberately stores both per-measurement (`palimpsest:runId` on the activity; optional
`palimpsest:parseRunId`) for per-triple reproducibility. But both closed shapes (Measurement,
Evidence) reject any predicate not in their allowlist, and neither lists a run id. The activity
blank node that currently hosts them is being removed. Pick ONE:

**Option A — run-provenance in a named graph (recommended).**
- *Mechanism:* the data graph (measurement + condition + evidence + paper) is SHACL-validated;
  run metadata is stored as **quads** in a separate `palimpsest:run/<run_id>` named graph keyed to
  the measurement IRI (`<m> palimpsest:runId <run_id>` etc.).
- *Pros:* data graph stays SHACL-clean; keeps per-triple run traceability; provenance gets a
  stable IRI (addresses review §4 "blank-node provenance isn't federatable"); standard pattern.
- *Cons:* `store.py` learns named graphs (`Quad(s, p, o, graph_name)`); `sparql()` / run-id queries
  need a `GRAPH` clause; the SHACL test must validate the default graph only.
- *Touches:* `store.py` (Quad graph arg + run-graph writer), `sparql()` doc, tests.

**Option B — run ids as schema slots.**
- *Mechanism:* add `run_id` / `parse_run_id` slots to `Evidence` (or a new `Activity` class) in
  `schema/palimpsest.yaml`, regenerate; they then sit legally on the (now non-rejecting) Evidence
  shape and pass closed validation.
- *Pros:* one graph, no named-graph machinery; semantically explicit; everything SHACL-validated.
- *Cons:* changes the schema contract T24 deliberately kept run ids OUT of ("CostMeter ledger
  concern, not a schema field"); `Evidence` becomes a mix of source-anchor + run bookkeeping;
  regen touches generated artifacts and the validation tests.
- *Touches:* `schema/palimpsest.yaml`, `schema/generated/*`, `store.py`, validation tests.

**Option C — drop run ids from the graph; recover from SQLite.**
- *Mechanism:* store only the schema data graph. Recover the **parse** run via
  `(paper_sha256, parser_name) → parser_runs.run_id` (`cache.py`).
- *Pros:* smallest, fully-conformant change; no schema or named-graph work.
- *Cons:* **the extraction `run_id` is lost entirely, not merely un-joinable.** `cost_ledger`
  has no `run_id` column (schema: `ts, kind, provider, amount_eur, detail`) and the extraction
  `run_id` is passed only as a function arg, today written solely on the activity blank node — which
  this task removes. So nothing in SQLite recovers it. Only `parser_runs.run_id` (the *parse* run)
  survives. This is the strongest case against Option C; it directly weakens the provenance
  non-negotiable.

**Recommendation:** Option A — keeps the provenance guarantee intact and SHACL-cleanly separates
data from run-bookkeeping, at the cost of named-graph handling. Confirm with Rahat/supervisor
before coding (this touches the "non-negotiable" provenance model).

## Verification
```bash
pixi run pytest tests/test_store.py tests/test_validation.py -v
# new test: inserted measurement subgraph -> pyshacl -> conforms == True
# (option A) run_id recoverable via a GRAPH-clause SPARQL query
```
MUST exit 0; the post-insert SHACL conformance test is the gate for this card.

## Will touch
- `src/palimpsest/store.py` (restructure `insert_extraction`: Evidence node, remove activity)
- `tests/test_store.py` (rewrite provenance-shape + count assertions; add SHACL-conformance test)
- (Option A) named-graph plumbing in `store.py`
- (Option B only) `schema/palimpsest.yaml` + `schema/generated/*` + `tests/test_validation.py`

## Will NOT touch
- `tools/extract.py`, `validation.py` logic (reuse `_shapes()` / `_to_jsonld` read-only)
- `schema/palimpsest.yaml` (unless Option B is chosen)
- `CLAUDE.md`, `PROGRESS.md`

## Out of scope
- Emitting H2KG's `Measurement→hasProperty/hasParameter` structural shape → later (needs this first).
- bbox-from-geometry / unit validation → T49.
- Removing the now-orphan `extracted_from`/`extracted_by`/`parsed_by` schema slots (review §3) →
  fold into T47 or a schema-cleanup card; out of scope here.

## Notes / references
- **Default approach: hand-build the new Evidence node** directly in `insert_extraction`, the same
  way every other node is built today (mint `palimpsest:measurement/<uuid>` and
  `palimpsest:paper/<sha256>` IRIs, set-dedup the Paper). Keep the deterministic IRIs — the return
  contract (`store.py` returns the measurement IRI; `tests/test_store.py` asserts it
  `startswith palimpsest:measurement/`) and Paper deduplication both depend on them.
- **Do NOT naively load `validation._to_jsonld(instance)` into the store.** It is tempting
  ("stored-form == validated-form by construction"), but `_to_jsonld` injects only `@type`, never
  `@id` — so every node parses as a **blank node**. That breaks (a) Paper dedup across measurements,
  (b) the measurement-IRI return contract, and (c) Option A, which keys the run-provenance named
  graph to the measurement IRI (you cannot key to a blank node). If you still want the
  by-construction guarantee, you must inject `@id` for the measurement (uuid, generated *before*
  parsing) and paper (sha256) into the JSON-LD first — at which point it is no simpler than
  hand-building.
- **Option B implementation note:** `run_id`/`parse_run_id` would have to become fields on the
  Pydantic `Evidence` model (populated at extraction time), since `insert_extraction` reads
  provenance from the instance — today `run_id` is a separate kwarg precisely because it is not a
  schema field.
- The current store links Paper twice (`wasDerivedFrom` + activity `prov:used`); the new model links
  it once, from Evidence via `palimpsest:paper`. Expect the triple count to drop on the prov side and
  the shape to change — update counts deliberately.
- This card closes C4 from `report/supervisor-update-2026-06-10.md`; it does **not** change the C1
  Condition behaviour already shipped in T46.
