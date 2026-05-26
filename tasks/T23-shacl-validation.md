# T23 — SHACL validation step

## Why
Belt-and-suspenders validation beyond Pydantic. SHACL catches semantic constraints (e.g. "an Overpotential must have a Condition with current_density") that Pydantic alone may miss.

## Input state
- T19 merged (shacl.ttl generated).
- T22 merged (extraction returns Pydantic instances).

## Output state
- File `src/palimpsest/validation.py` (replaces empty stub) exports:
  - `def validate_instance(instance: BaseModel) -> tuple[bool, str]` — converts instance to JSON-LD using the generated context, runs pyshacl against `schema/generated/shacl.ttl`, returns (ok, report).
  - `def validate_batch(instances: list[BaseModel]) -> list[tuple[BaseModel, bool, str]]`.
- File `tests/test_validation.py` covers:
  - Valid Overpotential with all required slots → ok = True.
  - Invalid Overpotential missing condition → ok = False, report mentions the missing slot.

## Verification
```bash
pixi run pytest tests/test_validation.py -v
```

## Will touch
- `src/palimpsest/validation.py` (full)
- `tests/test_validation.py` (new)

## Will NOT touch
- schema/generated/ (regenerated only by T19).
- extract.py (T22 stable). T24 will wire validation into the insert flow.

## Out of scope
- Inserting into graph → T24.

## Notes / references
- pyshacl docs: https://github.com/RDFLib/pySHACL
- Convert Pydantic → JSON-LD using `schema/generated/context.jsonld`. Use rdflib to parse JSON-LD.
- Reports can be verbose; for the test, just check the violation pattern matches expected (don't pin exact wording).
