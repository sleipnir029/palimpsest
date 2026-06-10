# T47 — align schema to H2KG (skos mappings)

## Why
Supervisor mandate. A concrete, low-risk "we integrated H2KG" artifact. The 2026-06-10 ground-check
confirmed H2KG v1.0.0 already defines 3 of our 4 hand-rolled local metrics; align to the official
terms and dual-anchor the rest. This also re-grounds the ontology-gap thesis chapter (T43).

## Input state
- `schema/palimpsest.yaml` as shipped (EMMO ECHO class_uris + QUDT unit mappings + local classes).
- H2KG namespace `https://w3id.org/h2kg/hydrogen-ontology#`, release IRI
  `https://w3id.org/h2kg/hydrogen-ontology/releases/1.0.0`.
- Ground-check confirmed these H2KG terms exist: `h2kg:TafelSlope`, `h2kg:MassActivity`,
  `h2kg:TurnoverFrequency`, `h2kg:Overpotential`, `h2kg:ExchangeCurrentDensity`,
  `h2kg:ChargeTransferCoefficient`, and "Electrochemically Active Surface Area" (+ `ECSA*` variants).
  Verified caveat: H2KG metrics are local `h2kg:Property` terms, **not** ECHO-IRI-anchored.

## Output state
- Add the `h2kg` prefix to the schema `prefixes` block.
- For the 3 currently-local metrics (TafelSlope, MassActivity, TurnoverFrequency): add a mapping to
  the H2KG term (`exact_mappings` or `close_mappings` — choose per the H2KG `dcterms:description`;
  exact only if definitions truly coincide).
- For the ECHO-bound metrics (Overpotential, ExchangeCurrentDensity, ECSA,
  ChargeTransferCoefficient): keep `class_uri` = ECHO IRI, add `close_mappings: [h2kg:…]`
  (dual-anchor — stays upper-ontology-aligned AND H2KG-discoverable).
- `OxygenEvolutionReaction`: keep the ECHO `AnodicReaction` close-mapping; add a comment that H2KG
  also lacks a native OER reaction class (shared-upstream gap, only `h2kg:OERPerformanceDataset`).
- Regenerate `schema/generated/*` via `pixi run schema`.
- Update `tests/test_schema_gen.py` / `tests/test_ontology.py` to assert the new `h2kg:` CURIEs
  resolve and appear in `schema/generated/context.jsonld`.

## Verification
```bash
pixi run schema
pixi run pytest tests/test_schema_gen.py tests/test_ontology.py -v
grep -c 'h2kg' schema/generated/context.jsonld   # > 0
```
The verification command MUST exit 0.

## Will touch
- `schema/palimpsest.yaml` (edit)
- `schema/generated/*` (regenerated)
- `tests/test_schema_gen.py`, `tests/test_ontology.py` (edit)

## Will NOT touch
- `store.py`, `tools/extract.py` (IRI mappings flow through schema → generated artifacts)
- `CLAUDE.md`, `PROGRESS.md`

## Out of scope
- Emitting `h2kg:` structural triples / H2KG's `Measurement→hasProperty→QuantityValue` shape →
  future work; needs T46 (conditions written) first.
- Entity-linking H2KG's 600+ leaf material/instrument terms → out of thesis scope; state as future
  work in T43.

## Notes / references
- H2KG metrics carry a `hasQuantityValue` node but no ECHO class IRI; our ECHO + per-slot QUDT
  bindings are the contribution back upstream. Record this framing in T43.
- Pin H2KG by its `owl:versionIRI` (`…/releases/1.0.0`) in a YAML comment so the dependency is
  dated and reproducible.
- Schema is "extensible by file, not by code" (CLAUDE.md) — these are mapping additions to existing
  classes, not new slots; no `exploratory.yaml` needed.
