# T24 — pyoxigraph insert with provenance triples

> **Status: ✓ landed 2026-06-08 (commits `5193e3a` + `f896a40`).** See "Resolved decisions" below for the deltas between this card and what shipped; the rest of the card is the original spec, preserved for historical context.

## Resolved decisions (2026-06-08, recorded in DEVIATIONS.md)

- **Signature slimmed.** Card spec was `insert_extraction(self, instance, paper_sha, page, bbox, parser_name, run_id, source_text="")`. After T19's audit + T18a F4 (per-corner bbox split), all 7 provenance fields are Pydantic-required on `Evidence`, so re-passing them duplicates work T22 already did. Shipped signature: `insert_extraction(instance, *, run_id, parse_run_id=None) -> str` — Evidence is pulled from `instance.evidence`, `run_id` stays explicit because it's not a schema field, `parse_run_id` is the optional second-run-id option (see next bullet).
- **Run_id semantics — both stored, distinct predicates.** Chose the second option from the original "DECIDE before coding" note: `palimpsest:runId` carries the extraction run_id on the PROV-O `prov:wasGeneratedBy` activity; optional `palimpsest:parseRunId` carries the parse run_id so a parse → triple chain is recoverable per-triple without joining through `parser_runs`.
- **Bbox provenance is 4 typed predicates, not a comma-joined string.** Card's "Notes" suggested `palimpsest:bbox` as the literal `"page,x0,y0,x1,y1"` for simplicity — that pre-dates T18a F4. Implementation emits 4 separate predicates on the activity blank node (`palimpsest:bboxX0`/`Y0`/`X1`/`Y1`, each `xsd:float`), matching Evidence's F4-split slots and avoiding the RDF-dedup vulnerability F4 fixed.
- **`store/` path default is in-memory.** Card's default was `path: str = "store/"`; shipped is `path: str | None = None` so `RDFStore()` is an in-memory `pyoxigraph.Store()` (zero side-effects for tests), and `RDFStore("store/")` opens RocksDB on disk. Existing `.gitignore` already excludes `store/`.

## Why
Validated instances must land in the triple store with full provenance (paper, parser, page, bbox, run_id) — every measurement traceable to its source glyph.

## Input state
- T18 (schema with EMMO IRIs), T22 (extraction), T23 (validation) merged.

## Output state
- File `src/palimpsest/store.py` (replaces stub) exports:
  - Class `RDFStore`:
    - `__init__(self, path: str = "store/")` — opens pyoxigraph RocksDB store at `path`.
    - `def insert_extraction(self, instance: BaseModel, paper_sha: str, page: int, bbox: tuple[float,float,float,float], parser_name: str, run_id: str, source_text: str = "") -> str` — returns subject IRI of the inserted measurement.
    - Each measurement gets a UUID-based IRI under `palimpsest:measurement/{uuid}`.
    - Provenance triples added: `prov:wasDerivedFrom` → paper IRI; `prov:wasGeneratedBy` → activity blank node with `prov:used` → paper IRI, `palimpsest:page`, `palimpsest:bbox`, `palimpsest:parserName`, `palimpsest:runId`, `palimpsest:sourceText`.
    - **DECIDE before coding — `run_id` semantics (two run_ids exist).** A parse produces `parser_runs` rows each stamped with a *parse* `run_id` (set per batch in `parse_with_cache`, T16); an *extraction* run then turns a parser's cached output into triples. So a triple has two candidate ids: (a) the extraction run that generated it, (b) the parse run its source text came from. Options: pass only the **extraction** run_id (the PROV-O `prov:wasGeneratedBy` activity — recommended for `palimpsest:runId`) and recover the parse via `(paper_sha, parser_name)` → `parser_runs`; OR additionally store the parse run_id as `palimpsest:parseRunId` for exact parse→triple traceability (recommended for reproducibility). Do NOT silently reuse one id for both meanings — pick, and make the chosen semantics explicit in the docstring.
    - `def sparql(self, query: str) -> list[dict]` — runs SPARQL query, returns list of binding dicts.
  - Module-level constants for namespaces: `PALIM = "https://w3id.org/palimpsest/"`, `EMMO_ECHO = "..."`, etc.
- File `tests/test_store.py` covers:
  - Insert a sample Overpotential instance. Confirm 1 measurement triple + ≥5 provenance triples added.
  - SPARQL `SELECT ?v WHERE {?m a palim:Overpotential; palim:value ?v.}` returns the value.

## Verification
```bash
pixi run pytest tests/test_store.py -v
```

## Will touch
- `src/palimpsest/store.py` (full)
- `tests/test_store.py` (new)

## Will NOT touch
- ontology.py (T18 stable).
- validation.py (T23 stable). T25 will wire them together.

## Out of scope
- The combined extract → validate → insert pipeline → T25.
- The viewer's bbox-hover endpoint → T30/T31.

## Notes / references
- pyoxigraph docs: https://pyoxigraph.readthedocs.io/
- Use `oxigraph.Store(path)` for persistent RocksDB storage.
- JSON-LD round-trip: serialize Pydantic with the context, parse via rdflib, dump triples into pyoxigraph. OR write a direct converter from Pydantic to triples (faster, less elegant — fine for MVP). **Chose the direct converter** — Pydantic's `model_dump` + a per-instance `Quad`-building loop is ~155 LOC; round-tripping through rdflib would add the parser overhead per-insert without a correctness gain since `validate_instance` (T23) already runs the JSON-LD route.
- ~~Provenance bbox stored as a literal string `"page,x0,y0,x1,y1"` for simplicity; if richer is needed later, refactor.~~ Superseded by T18a F4 (2026-06-08): bbox is 4 typed `xsd:float` predicates on the activity node, mirroring Evidence's `bbox_x0`/`bbox_y0`/`bbox_x1`/`bbox_y1` slots.
- pyoxigraph API quirks discovered during impl (in case a future card reuses the same patterns): `QuerySolution` is indexed positionally (`sol[0]`) or by Variable (`sol[Variable("o")]`), NOT via `sol.variables` — the outer `QuerySolutions` wrapper carries `.variables`. `xsd:float` literals canonicalize ("236.0" → "236" round-trip); tests should assert numerically (`float(rows[0]["v"]) == 236.0`), not pin the textual form. LinkML's `linkml_meta` exposes `.root`, not `.value` — `_class_iri` reads `type(instance).linkml_meta.root["class_uri"]`.
