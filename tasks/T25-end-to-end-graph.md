# T25 — end-to-end: 1 paper → graph + SHACL pass

## Why
First complete vertical slice. Proves: PDF → 4 parsers cached → extraction → validation → graph insert → SPARQL query returns the expected value.

## Input state
- T16, T22, T23, T24 merged.
- At least one paper has all 4 cached parser outputs.
- Ground truth: Rahat has read the sample paper and knows that the headline overpotential is, say, 236 mV @ 10 mA/cm² (verify against actual paper).

## Output state
- File `src/palimpsest/pipeline.py` exports:
  - `def run_paper(pdf_path: Path, parser_name: str = "mineru", skill_name: str = "oer-extraction") -> dict`:
    1. Parse via `parse_with_cache` (cache hit if already done).
    2. Extract via `extract`.
    3. Validate each instance via `validate_instance`. Drop invalid; log violations.
    4. Insert each valid instance via `RDFStore.insert_extraction` with provenance.
    5. Return summary dict: `{"paper_sha": ..., "n_extracted": ..., "n_validated": ..., "n_inserted": ...}`.
- File `tests/test_pipeline.py` runs against the sample paper, asserts:
  - `n_inserted >= 5`.
  - SPARQL query `SELECT ?val WHERE {?m a palim:Overpotential; palim:value ?val.}` returns at least one row with value close to ground-truth (within 10%).
- Update `__main__.py` so `pixi run python -m palimpsest demo papers/<sample>.pdf` runs the pipeline and prints a summary.

## Verification
```bash
pixi run python -m palimpsest demo papers/<sample>.pdf
pixi run pytest tests/test_pipeline.py -v
```

## Will touch
- `src/palimpsest/pipeline.py` (new)
- `src/palimpsest/__main__.py` (edit: add `demo` subcommand)
- `tests/test_pipeline.py` (new)

## Will NOT touch
- Any individual src module already implemented. This task is integration only.

## Out of scope
- Multi-paper batching → comes for free via parse_with_cache; can be tested in T34.
- TUI → T26.
- Viewer → T29.

## Notes / references
- This is the first task where you should see real numbers in the graph. Cherish it.
- If the SPARQL query returns wrong values, debug bottom-up: parser output → extracted Pydantic → triples → query. Do NOT bandaid the test; fix the actual bug.
- Cost on a single paper full pipeline: < €0.40 (or much less on cache hit).
