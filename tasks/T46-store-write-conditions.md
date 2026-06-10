# T46 — store writes Condition nodes + reconcile schema↔store (C1+C4)

## Why
Fix the top correctness gap surfaced in the 2026-06-10 review. `insert_extraction` drops
`instance.condition` (current density, electrode potential vs RHE, temperature, cell type, scan
rate, electrolyte). A measurement without its conditions is not a comparable datum, and conditions
are the prerequisite for any H2KG export (H2KG's model is `Measurement → hasParameter → Parameter`).
Also reconcile the stored predicates with the schema's `palimpsest:condition` /
`prov:hadPrimarySource` model so the persisted graph matches what SHACL validates (C4: today the
store emits `prov:wasDerivedFrom`/`wasGeneratedBy` and omits `condition`, so SHACL guarantees
nothing about the actual graph).

## Input state
- T24 merged (`store.py` as shipped). `schema/palimpsest.yaml` already defines `Condition` and
  `Electrolyte` classes and the `condition` slot on the measurement classes.
- A validated Overpotential instance carries `.condition` (a `Condition`) populated by T22.

## Output state
- `src/palimpsest/store.py` `insert_extraction` additionally emits, when `instance.condition` is set:
  - a `Condition` node (UUID IRI) linked from the measurement via `palimpsest:condition`
    (matching the schema `slot_uri`), typed `palimpsest:Condition`;
  - its scalar slots (`current_density`, `electrode_potential_vs_rhe`, `temperature_C`,
    `cell_type`, `scan_rate`) as typed literals;
  - an `Electrolyte` sub-node (`formula`, `concentration`, `electrolyte_ph`) when present.
- **Decide + document in the docstring (one model only):** either keep
  `prov:wasDerivedFrom`/`wasGeneratedBy` for provenance AND add `palimpsest:condition` for datum
  context, OR migrate provenance onto an IRI activity so the stored node validates against the
  shipped closed SHACL shape. The acceptance bar is **validated-form == stored-form**.
- `tests/test_store.py`:
  - assert a populated Overpotential inserts a `palimpsest:condition` edge and the Condition node's
    `current_density` is retrievable via SPARQL;
  - add a **post-insert SHACL check**: serialize the inserted measurement subgraph and run
    `pyshacl` against `schema/generated/shacl.ttl` → `conforms == True` (closes C4).

## Verification
```bash
pixi run pytest tests/test_store.py -v
# includes the new post-insert SHACL conformance test
```
The verification command MUST exit 0.

## Will touch
- `src/palimpsest/store.py` (edit)
- `tests/test_store.py` (edit)

## Will NOT touch
- `schema/palimpsest.yaml` (the Condition/Electrolyte slots already exist)
- `tools/extract.py`, `validation.py`
- `CLAUDE.md`, `PROGRESS.md` (PROGRESS only at merge time)

## Out of scope
- H2KG predicate retargeting → T47 maps IRIs; the structural export shape can stay
  palimpsest-native for now.
- Bbox / unit correctness → T49.

## Notes / references
- This is the C1+C4 fix from `report/supervisor-update-2026-06-10.md` (and the plan file). Keep it
  surgical — roughly 40–70 LOC in `store.py`.
- The existing test pins an exact triple count (18 for a populated Overpotential). Adding Condition
  triples will change it — update the count **deliberately** to the new expected value; do not
  bandaid the assertion.
- If you take the IRI-activity route, blank-node provenance becomes an IRI (also helps future
  federation, see review §4).
