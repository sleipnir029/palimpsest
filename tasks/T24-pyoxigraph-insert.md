# T24 — pyoxigraph insert with provenance triples

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
- JSON-LD round-trip: serialize Pydantic with the context, parse via rdflib, dump triples into pyoxigraph. OR write a direct converter from Pydantic to triples (faster, less elegant — fine for MVP).
- Provenance bbox stored as a literal string `"page,x0,y0,x1,y1"` for simplicity; if richer is needed later, refactor.
