---
name: pemwe-anode
description: Extract PEMWE-anode catalyst performance from PEM water-electrolyzer papers. Reuses the OER single-electrode metrics (overpotential, Tafel slope, mass activity, stability, ECSA, TOF, specific activity, exchange current density) and adds the full-cell quantities single-electrode OER papers lack — cell voltage and voltage degradation rate — plus MEA context (catalyst loading, membrane). Use when the paper reports single-cell / MEA / full-cell PEMWE data, not only three-electrode RDE.
when_to_use: paper_topic in {PEMWE, PEM_water_electrolysis, MEA, single_cell, full_cell, anode_durability, IrO2, RuO2, iridium_oxide}
version: 1.0.0
# T69 machine-readable alignment: the schema Measurement classes this skill
# extracts. The gate (src/palimpsest/skill_check.py) checks each against
# schema/palimpsest.yaml at load. This skill is an OVERLAY on oer-extraction:
# the 8 single-electrode classes are reused as-is; PEMWECellVoltage and
# DegradationRate are the T71 additions that make the full-cell story queryable.
targets:
  - Overpotential
  - TafelSlope
  - MassActivity
  - TurnoverFrequency
  - ECSA
  - ExchangeCurrentDensity
  - SpecificActivity
  - Stability
  - PEMWECellVoltage
  - DegradationRate
ontology: h2kg
---

# PEMWE-anode extraction playbook

You are extracting performance variables for **PEM water-electrolyzer anode
catalysts** (Ir / Ru oxides for acidic OER) into the palimpsest LinkML schema.
These papers test the same acidic-OER catalysts the `oer-extraction` skill
covers, but at **device scale** — in a membrane-electrode assembly (MEA) / single
cell — so they report two things single-electrode RDE papers cannot: the **full-
cell voltage** and its **degradation rate** over long holds. Be conservative: if
the paper does not state the **measurement conditions** required for a variable,
do **not** emit that variable.

## Single-electrode metrics (reused from OER — same conventions)

PEMWE-anode papers usually also report three-electrode RDE characterization of
the same catalyst. Emit these exactly as in OER extraction — one `Measurement`
per (variable, conditions) tuple, canonical units, disambiguating conditions:

| Reported variable | Schema target | Required conditions |
|---|---|---|
| Overpotential (η, mV vs RHE) | `Overpotential` (`mV`) | `current_density` (10 mA/cm² is the RDE benchmark); `electrolyte`; `iR_correction` |
| Tafel slope (mV/decade) | `TafelSlope` | fit-range `current_density`; `iR_correction` |
| Mass activity (A g⁻¹ active metal) | `MassActivity` (`A/g`) | `electrode_potential_vs_rhe` (e.g. 1.53 V vs RHE) |
| Turnover frequency (s⁻¹) | `TurnoverFrequency` (`1/s`) | `electrode_potential_vs_rhe`; site-counting method (free-text) |
| ECSA (cm² geometric) | `ECSA` (`cm2`) | method (Cdl / redox integration) |
| Exchange current density (mA/cm²) | `ExchangeCurrentDensity` | Tafel extrapolation range; `electrolyte` |
| Specific activity (mA cm⁻²_ECSA) | `SpecificActivity` (`mA/cm2`) | `electrode_potential_vs_rhe` |
| Stability (h) | `Stability` (`h`) | hold `current_density`; cell type (RDE vs single-cell) |

`iR_correction` is the usual RDE trap: record `unknown` when not stated, never
`not_applied`. Geometric vs ECSA-normalized `j`, scan rate, and electrolyte
(0.5 M H₂SO₄ / 0.1 M HClO₄ / 1 M HClO₄) all change what a number means — record
the disambiguating condition. See the `oer-extraction` references for Tafel sign
convention and acidic-OER protocol detail.

## Full-cell metrics (the T71 additions — the reason this skill exists)

These are **cell-level**, not electrode-level. Do not conflate them with the
single-electrode metrics above.

| Reported variable | Schema target | Required conditions |
|---|---|---|
| PEMWE cell voltage (V) | `PEMWECellVoltage` (`V`) | cell `current_density` (A/cm², record in `current_density`); `temperature_C` (75–80 °C typical); anode `catalyst_loading` (mg/cm² Ir); membrane (free-text in `cell_type`) |
| Voltage degradation rate | `DegradationRate` (`mV/h`) | hold `current_density` (A/cm²); test duration; `temperature_C` |

### `PEMWECellVoltage`
- The full-cell voltage at a stated **cell** current density (community points:
  Vcell @ 1 A cm⁻², Vcell @ 2 A cm⁻²; SOA targets ≤ 1.75 V @ 2 A cm⁻²).
- **Vcell is NOT an overpotential.** A "1.75 V" full-cell figure and a "240 mV"
  RDE overpotential are different quantities for the same catalyst — emit the
  former as `PEMWECellVoltage`, never as `Overpotential`.
- Almost always **iR-uncorrected** (full cell voltage is what matters); record
  `iR_correction: unknown` unless the paper states otherwise.
- Put the operating current density (A/cm²) in `condition.current_density` — the
  same slot the RDE benchmark uses, distinguished by magnitude (A/cm² vs mA/cm²)
  and by the `cell_type`/`cell_type_family` (`single_cell_MEA`).

### `DegradationRate`
- Rate of cell-voltage rise during a durability hold. Canonical unit **mV/h**.
- Papers report it as **µV h⁻¹** (e.g. 22 µV/h) or **mV per 1000 h** (e.g.
  126 mV/1000 h). **Convert to mV/h before emitting**: 22 µV/h → 0.022 mV/h;
  126 mV/1000 h → 0.126 mV/h.
- A degradation rate is meaningless without its **hold current density** and
  **duration** — record both. Do not fuse a 1 A cm⁻² and a 2 A cm⁻² rate.

### `catalyst_loading` (a condition, not a measurement)
- Anode Ir loading (mg/cm²) is the defining MEA parameter for cost — record it
  on `condition.catalyst_loading` for cell-level measurements (typical 0.1–2
  mg cm⁻² Ir; low-loading ≤ 0.4 is the headline). It is an experimental
  parameter, never a `Measurement`.

See `references/pemwe-anode-protocols.md` for the single-cell operating
envelope, membrane families, and durability/AST conventions.

## Common traps

1. **Vcell vs η** — full-cell voltage (V) is not an overpotential (mV). Keep them
   in separate classes.
2. **Cell vs RDE current density** — A cm⁻² (cell) vs mA cm⁻² (RDE); a "2" with
   the wrong unit is a 1000× error. Record the unit faithfully; emit in the
   canonical unit.
3. **Cited-literature vs own data** — comparator values from other papers
   ("vs Ir/Sb-SnO₂ 15 h") are not this paper's measurements. Exclude them.
4. **Theoretical / DFT values** — computed overpotentials or voltages are not
   experimental measurements. Exclude them.
5. **Degradation-rate units** — µV/h vs mV/h vs mV/1000h differ by 10³–10⁶.
   Always convert to mV/h.

## Output discipline

- One `Measurement` per (variable, conditions) tuple. Do not collapse values
  reported under different conditions.
- Every `Measurement` MUST carry `Evidence` with `paper.sha256`, `page`, the four
  per-corner bbox floats (`bbox_x0`, `bbox_y0`, `bbox_x1`, `bbox_y1`), and
  `parser_name`. Without all, do not emit the triple.
- `unit_label` on `Measurement` is the unit as printed in the paper; convert the
  value to the canonical unit shown in the normalization rules before emitting.
