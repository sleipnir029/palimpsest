# T18 — LinkML schema with EMMO + QUDT + palimpsest-local IRIs

## Why
One source of truth for all data structures. Generates Pydantic, JSON Schema, JSON-LD context, and SHACL shapes.

## Input state
- T17 merged.
- `schema/` directory exists but empty.
- `pixi run linkml --version` succeeds.

## Output state
- File `schema/palimpsest.yaml` exists with:
  - `id: https://w3id.org/palimpsest/v1`
  - `name: palimpsest`
  - `prefixes:` block with `emmo`, `qudt`, `prov`, `schema`, `palimpsest`, `xsd`, `linkml`.
  - `default_prefix: palimpsest`
  - `imports: [linkml:types]`
  - `classes:` covering at minimum: `Paper`, `Measurement` (abstract), `Overpotential`, `TafelSlope`, `ExchangeCurrentDensity`, `ChargeTransferCoefficient`, `MassActivity`, `TurnoverFrequency`, `ECSA`, `Catalyst`, `Electrolyte`, `Condition` (with current_density, potential_vs_RHE, temperature_C, electrolyte, cell_type), `Evidence` (with paper, page, bbox, source_text, parser_name), `OxygenEvolutionReaction`.
  - Each slot has explicit `slot_uri` pointing to EMMO when available, palimpsest-local otherwise.
  - Each slot has `unit:` block (QUDT IRI) where applicable.
  - Slots that close-match an EMMO concept have `exact_mappings` or `close_mappings` with the EMMO IRI.
  - Comments `# TODO_EMMO_UPSTREAM: ...` mark places where palimpsest-local IRIs are used (OER reaction, Tafel slope, mass activity, TOF).
- File `src/palimpsest/ontology.py` exports:
  - `EMMO_ECHO = "https://w3id.org/emmo/domain/electrochemistry"`
  - `@cache def emmo_iri(class_label: str) -> str | None` — loads ECHO graph, finds IRI by `rdfs:label`.
  - `KNOWN_IRIS: dict[str, str]` — hard-coded mapping for the verified IRI hashes from design doc Appendix E (Overpotential, ActivationOverpotential, AnodicOverpotential, Electrocatalyst, ButlerVolmerEquation, etc.). Each entry has a unit test verifying the IRI resolves.
- File `tests/test_ontology.py` covers:
  - `emmo_iri("Overpotential")` returns the verified hash.
  - All KNOWN_IRIS entries resolve to non-None.

## Verification
```bash
pixi run linkml-validate schema/palimpsest.yaml
pixi run pytest tests/test_ontology.py -v
```
Both must exit 0.

## Will touch
- `schema/palimpsest.yaml` (new)
- `src/palimpsest/ontology.py` (full implementation)
- `tests/test_ontology.py` (new)

## Will NOT touch
- Any other src file.
- pixi.toml.

## Out of scope
- Generating Pydantic / SHACL → T19.
- Exploratory schema additions → T22 (slot proposal flow).

## Notes / references
- Design ref: Appendix E (full IRI table). Use it verbatim for the mappings.
- Verified EMMO ECHO IRIs (from design doc): Overpotential = `electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6`, etc.
- Use LinkML's `unit:` block per https://linkml.io/linkml/schemas/metadata.html
- For `OxygenEvolutionReaction` and `TafelSlope`, use `palimpsest:OxygenEvolutionReaction` / `palimpsest:TafelSlope` with `close_mappings` to EMMO's AnodicReaction / ButlerVolmerEquation respectively, and a `# TODO_EMMO_UPSTREAM:` comment.
- Aim for ~30 classes and slots. Do not over-engineer. New slots can be added via `schema/exploratory.yaml` in T22.
