---
name: oer-extraction
description: Extract OER catalyst performance variables (overpotential, Tafel slope, mass activity, TOF, ECSA, exchange current density, stability, PEMWE cell voltage) from PEM electrolyzer / acidic water-splitting papers. Use when paper topic is OER, PEMWE, IrO2, RuO2, or oxygen evolution.
when_to_use: paper_topic in {OER, PEMWE, acidic_water_splitting, iridium_oxide, ruthenium_oxide}
version: 1.0.0
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

| Schema slot | Required conditions |
|---|---|
| `overpotential` (η, mV vs RHE) | current density `j` (mA cm⁻² or A cm⁻²); electrolyte; iR-correction status |
| `tafel_slope` (mV/decade) | fit current-density range; iR-correction status |
| `mass_activity` (A g⁻¹ of active metal, e.g. A g⁻¹Ir) | potential vs RHE at which it is reported |
| `turnover_frequency` (TOF, s⁻¹) | potential vs RHE; site-counting method (assumed all-metal-surface vs ECSA-derived vs in-operando) |
| `ecsa` (cm² or m² g⁻¹) | method (Cdl from CV at non-faradaic potentials; Pb-UPD; surface-redox integration) |
| `exchange_current_density` (j₀, A cm⁻² or mA cm⁻²) | Tafel extrapolation range; electrolyte |
| `stability_hours` (h) | hold current density (mA cm⁻² for RDE, A cm⁻² for PEMWE); cell type (RDE vs single-cell PEMWE); degradation rate if reported (µV h⁻¹) |
| `pemwe_cell_voltage` (V) | current density (A cm⁻²); temperature; anode and cathode catalyst loadings (mg cm⁻²); membrane (e.g. Nafion 117/115/212) |

## Default operating points

When a paper reports a single headline number, it almost always refers to one
of these community defaults. Use these as **defaults** when the paper is
explicit, never as **assumptions** when it is not.

- **η@10 mA cm⁻²** — the de-facto RDE / three-electrode benchmark for
  electrocatalyst comparison (Jaramillo / McCrory convention).
- **η@100 mA cm⁻²** — high-performing acidic OER catalysts; emerging RDE
  benchmark for state-of-the-art Ir / Ru oxides.
- **η@1 A cm⁻² or η@2 A cm⁻²** — PEMWE single-cell operating points.
  Industrial-relevant; almost always with iR-correction *not* applied (full
  cell voltage is what matters).
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
   resistance subtracted). PEMWE Vcell values almost never are. If the paper
   does not state correction status, record it as `iR_correction = unknown`,
   not as `false`.
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
  `bbox`, and `parser_name` (T18 schema required fields). Without all four,
  do not emit the triple.
- Free-text `unit_label` on `Measurement` is for the unit as printed in the
  paper (e.g. `"mV"`, `"A g⁻¹_Ir"`); the canonical unit lives on the slot
  definition.
