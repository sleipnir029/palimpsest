# T43 — Thesis chapter: ontology gap analysis

> **Re-grounded against H2KG (2026-06-10).** The gap analysis must now be framed against the
> official H2KG v1.0.0 release, not EMMO ECHO alone. Ground-check finding: **H2KG already defines
> 3 of the 4 metrics this card lists as "palimpsest-local" — `h2kg:TafelSlope`,
> `h2kg:MassActivity`, `h2kg:TurnoverFrequency`.** So the contribution shifts from "EMMO lacks
> these" to a **coverage-mapping against a real community standard**: (1) align to H2KG where it
> covers us (the 3 metrics); (2) note the genuine remaining gap — **neither** EMMO ECHO **nor**
> H2KG defines OER as a native reaction class (H2KG has only `h2kg:OERPerformanceDataset`); both
> route through ECHO `AnodicReaction`; (3) the contribution back upstream is the **ECHO class-IRI +
> per-slot QUDT unit anchoring** that H2KG's local `h2kg:Property` metrics lack, plus the
> OER→`AnodicReaction` bridge. Depends on T47 (the schema-side alignment). See
> `report/supervisor-update-2026-06-10.md` and the H2KG ground-check.

## Why
A novel contribution: catalogue what the available ontologies (EMMO Domain Electrochemistry **and**
H2KG v1.0.0) cover and miss for OER literature, and what palimpsest contributes back.

## Input state
- T18 (schema) merged. The `# TODO_EMMO_UPSTREAM:` comments document the EMMO gaps.
- T47 (H2KG alignment) merged — the schema carries `h2kg:` mappings to compare against.

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
