# T18a — schema cleanups (non-blocking)

## Why
T19's audit (post-merge) surfaced two schema findings the team chose not to
block T20+ on. Tracked here so they don't get lost.

## Input state
- T19 merged. T18 patched in the same commit to mark Evidence.{paper,page,bbox,parser_name} required.
- `schema/palimpsest.yaml` validates and is the source of truth.
- All 4 generated artifacts in `schema/generated/` reflect the patched schema.

## Findings to resolve

### F1. `OxygenEvolutionReaction` is an empty marker class
- pydantic.py shows `class OxygenEvolutionReaction(ConfiguredBaseModel): pass` (zero slots).
- SHACL NodeShape has no `sh:property` blocks.
- JSON Schema `$defs.OxygenEvolutionReaction` has empty `properties`.
- **Decide:** keep as IRI placeholder (intentional — "this paper studies OER"),
  or add slots (catalyst reference, product, reaction equation). If keep,
  add a YAML comment explaining "intentionally slot-less".

### F2. JSON-LD context exposes 5 orphan slots not on any class
context.jsonld defines but no class lists in its `slots:`:
- `activation_overpotential` (emmo hash)
- `anodic_overpotential` (emmo hash)
- `overpotential_at_10mAcm2`
- `catalyst` (would-be relationship)
- `oer_reaction` (would-be relationship)

These three PROV-O slots are intentional (T24 constructs the triples directly,
not via pydantic fields), so they stay: `extracted_by`, `extracted_from`,
`parsed_by`.

**Decide per orphan slot:** delete from `slots:`, OR attach to a class. The
first three (overpotential variants) look like Appendix E rows that didn't
make it into any class's slot list. `catalyst` and `oer_reaction` look like
relationship slots a future Paper class would use.

### F3. Missing Measurement subclasses (surfaced by T20/T20.5 review, 2026-06-01)
The schema models metrics as Measurement subclasses (`Overpotential`,
`TafelSlope`, `ExchangeCurrentDensity`, `ChargeTransferCoefficient`,
`MassActivity`, `TurnoverFrequency`, `ECSA`) but does NOT yet declare:

- **`Stability`** — hours (h). Required conditions: hold `current_density`,
  `cell_type`; optional degradation rate (µV/h or mV per 1000 h).
- **`PEMWECellVoltage`** — V. Required conditions: `current_density` (A/cm²),
  `temperature_C`, anode/cathode catalyst loadings (mg/cm²), membrane id.
- (optional) **`SpecificECSA`** — m²/g. Distinguishes from geometric `ECSA`
  (cm²) which is already modeled.
- (optional) **`Pressure`** — bar. Condition slot, not a Measurement
  subclass, if cell-pressure ever matters for an experiment.

T20 SKILL.md teaches the LLM about these variables; T20.5 `normalize.py`
deliberately omits them from `UNIVERSAL_UNITS` until the schema declares
them. Until F3 lands, the LLM records these in free-text annotations only,
not as typed Measurement instances.

**Decide:** add classes inheriting from `Measurement` (mirror how
`Overpotential` / `TafelSlope` are declared), with `close_mappings` to EMMO
terms if any exist (otherwise palimpsest-local CURIEs). Add corresponding
entries to `UNIVERSAL_UNITS` in `normalize.py` in the same change.

## Output state
- `schema/palimpsest.yaml` no longer carries unreachable slots OR every slot has a clear class home.
- `OxygenEvolutionReaction` either gains slots or a `# intentionally slot-less` comment.
- `pixi run schema` regenerates clean (no LinkML warnings).
- Existing tests still green.

## Verification
```bash
pixi run linkml-validate schema/palimpsest.yaml
pixi run schema
pixi run pytest tests/test_schema_gen.py tests/test_ontology.py -v
```

## Will touch
- `schema/palimpsest.yaml` (edit)
- `schema/generated/*` (regen + re-add headers)

## Will NOT touch
- Anything in `src/palimpsest/`
- `tests/` (no new tests needed unless slots gain required markers)

## Out of scope
- Adding `run_id` as a new Evidence slot (T24 may want this; track separately)
- Marking Catalyst.name or Paper.sha256 as required (separate audit)
- Splitting Measurement into typed-vs-untyped variants (T22 may surface this)

## Notes / references
- Discovered during T19 audit pass (PROGRESS T19 line).
- CLAUDE.md provenance non-negotiable already enforced for Evidence in T19 patch — that's why this card is non-blocking.
- LinkML's gen-jsonld-context exports all `slots:` entries regardless of class usage; this is documented LinkML behavior, not a generator bug.
