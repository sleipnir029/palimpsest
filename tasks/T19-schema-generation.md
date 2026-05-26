# T19 — Schema generation pipeline

## Why
Pydantic models, SHACL shapes, JSON-LD context, JSON Schema all flow from one LinkML source.

## Input state
- T18 merged. `schema/palimpsest.yaml` validates.

## Output state
- `pixi.toml` `[tasks]` adds:
  - `schema-pydantic = "gen-pydantic schema/palimpsest.yaml > schema/generated/pydantic.py"`
  - `schema-shacl = "gen-shacl schema/palimpsest.yaml > schema/generated/shacl.ttl"`
  - `schema-jsonld = "gen-jsonld-context schema/palimpsest.yaml > schema/generated/context.jsonld"`
  - `schema-jsonschema = "gen-json-schema schema/palimpsest.yaml > schema/generated/jsonschema.json"`
  - `schema = { depends-on = ["schema-pydantic", "schema-shacl", "schema-jsonld", "schema-jsonschema"] }`
- `schema/generated/` populated with the 4 generated files.
- File `tests/test_schema_gen.py` covers:
  - `from schema.generated.pydantic import Overpotential` works.
  - `Overpotential(value=236.0, unit="qudt:MilliV", ...)` validates.
  - Generated SHACL is non-empty Turtle.

## Verification
```bash
pixi run schema
pixi run pytest tests/test_schema_gen.py -v
```

## Will touch
- `pixi.toml` (edit: add tasks)
- `schema/generated/pydantic.py` (generated)
- `schema/generated/shacl.ttl` (generated)
- `schema/generated/context.jsonld` (generated)
- `schema/generated/jsonschema.json` (generated)
- `tests/test_schema_gen.py` (new)

## Will NOT touch
- `schema/palimpsest.yaml` (T18 stable).

## Out of scope
- Validating against the schema → T23.
- Inserting into graph → T24.

## Notes / references
- LinkML CLI docs: https://linkml.io/linkml/generators/index.html
- `schema/generated/` should be regenerated, not hand-edited. Add a comment at the top of each file: `# GENERATED — DO NOT EDIT BY HAND. Run: pixi run schema`.
- Commit the generated files so users don't need to regenerate on clone.
