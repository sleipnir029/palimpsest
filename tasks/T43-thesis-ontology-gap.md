# T43 — Thesis chapter: ontology gap analysis

## Why
A novel contribution: catalogue what EMMO Domain Electrochemistry is missing for OER literature.

## Input state
- T18 (schema) merged. The `# TODO_EMMO_UPSTREAM:` comments document the gaps.

## Output state
- File `thesis/03_ontology_gap.md` containing:
  - Motivation: why ontology alignment matters for FAIR scientific data.
  - Current EMMO ECHO coverage: what's there (Overpotential, ActivationOverpotential, Butler-Volmer, ECSA, etc.).
  - Identified gaps:
    - `OxygenEvolutionReaction` — not in ECHO. Currently `palim:OxygenEvolutionReaction` with `close_mappings` to `emmo:AnodicReaction`.
    - `TafelSlope` / `TafelEquation` — not in ECHO. Currently `palim:TafelSlope` with `close_mappings` to `emmo:ButlerVolmerEquation`.
    - `MassActivity`, `TurnoverFrequency` — not in ECHO. Palimpsest-local.
    - Reference-electrode-qualified `ElectrodePotential` (vs RHE, vs SHE, vs Ag/AgCl) — palimpsest-local subclasses suggested.
  - Proposed additions to upstream EMMO: a table mapping each palimpsest-local IRI to a proposed EMMO class with parent (subClassOf).
  - Mechanism for upstream contribution: how to file an issue/PR on https://github.com/emmo-repo/domain-electrochemistry.
- Word count: 1500–2500 words.

## Verification
```bash
test -f thesis/03_ontology_gap.md
wc -w thesis/03_ontology_gap.md   # 1500–2500
grep -c "TODO_EMMO_UPSTREAM" schema/palimpsest.yaml   # ≥4 markers in schema
```

## Will touch
- `thesis/03_ontology_gap.md` (new)

## Will NOT touch
- schema/palimpsest.yaml.

## Out of scope
- Actually filing PRs against EMMO upstream (out of thesis scope; mention as future work).

## Notes / references
- 3 hours.
- This is a small but original contribution. Frame it carefully.
