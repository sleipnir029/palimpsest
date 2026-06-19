---
name: oer-extraction
description: Extract OER catalyst performance variables (overpotential, Tafel slope, mass activity, TOF, ECSA, exchange current density, stability, PEMWE cell voltage) from PEM electrolyzer / acidic water-splitting papers. Use when paper topic is OER, PEMWE, IrO2, RuO2, or oxygen evolution.
when_to_use: paper_topic in {OER, PEMWE, acidic_water_splitting, iridium_oxide, ruthenium_oxide}
version: 1.0.0
# T69 machine-readable alignment: the schema Measurement classes this skill
# extracts. The gate (src/palimpsest/skill_check.py) checks each against
# schema/palimpsest.yaml at load. "PEMWE cell voltage" (in the description) has
# no schema class yet (T18a F3) so it is NOT a target; ChargeTransferCoefficient
# exists in the schema but the body does not teach it, so it is not listed.
targets:
  - Overpotential
  - TafelSlope
  - MassActivity
  - TurnoverFrequency
  - ECSA
  - ExchangeCurrentDensity
  - SpecificActivity
  - Stability
ontology: h2kg
---

# OER extraction playbook

You are extracting performance variables for the oxygen evolution reaction
(OER) from acidic water-splitting / PEM electrolyzer literature into the
palimpsest LinkML schema. Be conservative: if the paper does not state the
**measurement conditions** required for a variable, do **not** emit that
variable — emit a missing-condition note instead.

## Required slots and their conditions

Every performance variable below MUST carry the conditions in parentheses or
it is meaningless. If the conditions are absent, skip the slot.

| Reported variable | Schema target (`schema/palimpsest.yaml`) | Required conditions |
|---|---|---|
| Overpotential (η, mV vs RHE) | `Overpotential` class — emit one item per kind (η@10 mA/cm², activation, anodic) with `value` + `unit_label="mV"`; disambiguate the kind via `condition.current_density` (10 mA/cm² for the benchmark) and/or the `evidence.source_text` quote (F2 dropped the typed sub-slots `overpotential_at_10mAcm2`/`activation_overpotential`/`anodic_overpotential` 2026-06-08) | `current_density` (mA/cm² or A/cm²); `electrolyte`; `iR_correction` ∈ {applied, not_applied, unknown} |
| Tafel slope (mV/decade) | `TafelSlope` class | fit-range `current_density` min/max; `iR_correction` |
| Mass activity (A g⁻¹ of active metal, e.g. A g⁻¹Ir) | `MassActivity` class (canonical unit `A/g`) | `electrode_potential_vs_rhe` at which it is reported |
| Turnover frequency (TOF, s⁻¹) | `TurnoverFrequency` class | `electrode_potential_vs_rhe`; site-counting method (all-metal-surface / ECSA-derived / in-operando — free-text annotation; no dedicated slot) |
| ECSA (cm² geometric) | `ECSA` class (canonical unit `cm2`; specific ECSA in m²/g is **not yet modeled** — see T18a F3) | method (Cdl from CV at non-faradaic potentials; Pb-UPD; surface-redox integration) |
| Exchange current density (j₀, mA/cm²) | `ExchangeCurrentDensity` class | Tafel extrapolation range; `electrolyte` |
| Specific activity (mA cm⁻²_ECSA) | `SpecificActivity` class (canonical unit `mA/cm2`; T52) — OER current normalized to ECSA | `electrode_potential_vs_rhe` at which it is reported (e.g. η=300 mV) |
| Stability (h) | `Stability` class (canonical unit `h`; T52, closes T18a F3) | hold `current_density` (mA/cm² for RDE; A/cm² for PEMWE); cell type (RDE vs single-cell PEMWE); degradation rate if reported (µV/h) |
| PEMWE cell voltage (V) | **No schema class yet — see T18a Finding F3**. Record as free-text annotation until added. | `current_density` (A/cm²); `temperature_C`; anode/cathode catalyst loadings (mg/cm²); membrane (e.g. Nafion 117/115/212) |

## Default operating points

When a paper reports a single headline number, it almost always refers to one
of these community defaults. Use these as **defaults** when the paper is
explicit, never as **assumptions** when it is not.

- **η@10 mA cm⁻²** — the de-facto RDE / three-electrode benchmark for
  electrocatalyst comparison (Jaramillo / McCrory convention).
- **η@100 mA cm⁻²** — high-performing acidic OER catalysts; emerging RDE
  benchmark for state-of-the-art Ir / Ru oxides.
- **Vcell @ 1 A cm⁻² or Vcell @ 2 A cm⁻²** — PEMWE single-cell operating
  points. These are **cell voltages**, not overpotentials; industrial-relevant.
  Almost always with iR-correction *not* applied (full cell voltage is what
  matters).
- **Tafel fit range** — typically the low-overpotential linear region
  (50–150 mV above the OER onset). If the paper fits across a wide range that
  spans transport-limited current, flag it.

## Tafel slope conventions

- Units: **mV decade⁻¹**. Report exactly that. Some papers give V dec⁻¹ —
  convert to mV.
- Report the **current-density range** used for the fit. A 40 mV/dec slope
  over 0.1–1 mA cm⁻² is a different claim than 40 mV/dec over 1–10 mA cm⁻².
- Sign convention: report the **magnitude** (positive). The Tafel equation
  uses `η = a + b·log(j)`; `b` is positive for OER.
- See `references/tafel-conventions.md` for sign / intercept details.

## Mass activity

- Units: **A g⁻¹ of active metal**, e.g. A g⁻¹Ir or A g⁻¹Ru. Some papers use
  A mg⁻¹ — convert.
- **Always specify the potential** at which the mass activity is reported
  (usually 1.50 V or 1.53 V vs RHE for acidic OER).
- Mass loading on the electrode must be given (mg cm⁻²) so the reader can
  recompute geometric `j` from mass activity.

## Stability

- Units: **hours**. Report the **hold current density** and the **cell type**
  (RDE chronopotentiometry vs PEMWE single-cell durability).
- Degradation rate if reported: µV h⁻¹ for PEMWE; mV per 1000 h for long
  tests.
- A 10-h RDE hold and a 1000-h PEMWE hold are not comparable; never fuse them.
- See `references/pemwe-protocols.md` for typical PEMWE durability protocols.

## Mechanism annotations

If the paper makes mechanistic claims, record them as boolean / categorical
flags (not as numbers):

- **AEM** — adsorbate evolution mechanism (concerted proton–electron
  transfers on metal sites, no lattice oxygen exchange).
- **LOM** — lattice oxygen mechanism (lattice O participates; often
  evidenced by ¹⁸O isotope labelling, pH-dependent activity, in-situ
  spectroscopy).
- **WNA** — water nucleophilic attack on a metal-oxo intermediate.

Mechanism claims are usually evidence-based (DFT + isotope + operando
spectroscopy); flag the evidence type alongside the claim.

## Common traps

These cause the **same number to mean different things** across papers.
Always record the disambiguating field.

1. **iR-correction**: RDE η values are commonly iR-corrected (cell
   resistance subtracted). PEMWE Vcell values almost never are. The
   `iR_correction` enum has three values — `applied`, `not_applied`,
   `unknown`. If the paper does not state correction status, record it as
   `unknown`, not as `not_applied`.
2. **Scan rate**: η extracted from a fast CV (50–100 mV s⁻¹) differs from
   η extracted from a slow LSV (1–10 mV s⁻¹) or steady-state staircase.
   Record the scan rate or the technique.
3. **Geometric vs ECSA-normalized j**: geometric `j` divides by electrode
   geometric area; specific `j` divides by ECSA. A paper reporting η@10 mA
   cm⁻²_ECSA is making a much stronger claim than η@10 mA cm⁻²_geom for the
   same material. Record which normalization applies.
4. **Electrolyte**: 0.5 M H₂SO₄ vs 0.1 M HClO₄ vs 1 M HClO₄ — common acidic
   electrolytes give different OER kinetics. Record the electrolyte.
5. **Catalyst loading**: same intrinsic catalyst at 0.1 vs 1.0 mg cm⁻² gives
   different η. Record loading.

## Output discipline

- One `Measurement` per (variable, conditions) tuple. Do not collapse two
  values reported under different conditions into one slot.
- Every `Measurement` MUST carry `Evidence` with `paper.sha256`, `page`,
  the four per-corner bbox floats (`bbox_x0`, `bbox_y0`, `bbox_x1`, `bbox_y1`,
  page-relative; F4 split bbox into 4 typed slots so SHACL cardinality is
  dedup-safe), and `parser_name` (T18 schema required fields). Without all,
  do not emit the triple.
- Free-text `unit_label` on `Measurement` is for the unit as printed in the
  paper (e.g. `"mV"`, `"A g⁻¹_Ir"`); the canonical unit lives on the slot
  definition.
