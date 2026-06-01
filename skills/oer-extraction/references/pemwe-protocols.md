# PEMWE test protocols (acidic single-cell)

Proton-exchange membrane water electrolyzer (PEMWE) single-cell testing is
where acidic OER catalysts prove themselves at industrial-relevant current
densities. Conditions are tightly clustered around community defaults; record
deviations explicitly.

## Default operating envelope

- **Temperature**: 75–80 °C (cell body / endplate temperature). Lower is
  uncommon; 60 °C is sometimes reported for stability tests.
- **Feed**: deionized water (≥ 1 MΩ cm or ≥ 18 MΩ cm depending on lab) fed
  to the anode at 1–50 mL min⁻¹. Some labs feed both sides; most feed anode
  only.
- **Membrane**: Nafion 117 (~178 µm, durability tests), Nafion 115 (~127 µm),
  or Nafion 212 (~50 µm, performance tests). Reinforced membranes (Aquivion,
  Gore) appear in recent literature.
- **Anode (OER) catalyst layer**: Ir-based (IrO₂, IrOₓ, Ir-Ru oxides). Loadings
  range 0.1–2 mg cm⁻² Ir. Low-loading (≤ 0.4 mg cm⁻² Ir) is the headline
  metric for cost reduction.
- **Cathode (HER) catalyst layer**: Pt/C, typically 0.1–0.5 mg cm⁻² Pt.
- **Binder**: Nafion ionomer, 10–30 wt% in the catalyst layer.
- **Porous transport layer (anode)**: Pt- or Au-coated Ti felt / sintered Ti
  fiber. Uncoated Ti passivates; record coating if reported.

## Polarization curve

- Typical sweep: 0 to 2.0–2.5 V cell voltage, current-controlled (galvanostatic
  staircase) or potential-controlled (slow LSV, 1–10 mV s⁻¹).
- Steady-state holds: 60–300 s per current density step for accurate
  steady-state Vcell.
- Performance metrics to record:
  - `pemwe_cell_voltage` at `j = 1 A cm⁻²` (entry-level benchmark)
  - `pemwe_cell_voltage` at `j = 2 A cm⁻²` (high-current benchmark; SOA
    catalysts target ≤ 1.75 V here)
  - Sometimes `j` at fixed `Vcell` (e.g. j @ 1.8 V).

## Durability

- Constant-current hold at 1, 2, or 3 A cm⁻² for hundreds to thousands of
  hours.
- Report degradation rate as **µV h⁻¹** (instantaneous slope of Vcell vs
  time) or as **mV per 1000 h** for long campaigns.
- Accelerated stress tests (AST): cycling between OCV and high current,
  square-wave voltage holds, or start/stop cycles. Record the AST protocol
  (e.g. "DOE 1.4–2.0 V square-wave AST").

## What to record

For every PEMWE measurement, capture:

- temperature (°C)
- membrane identity (e.g. "Nafion 117")
- anode loading (mg cm⁻² of the active metal, e.g. mg cm⁻² Ir)
- cathode loading (mg cm⁻² Pt)
- iR-correction status (almost always **uncorrected** for PEMWE Vcell —
  unlike RDE η)
- active area (cm²)
- current density of the hold or sweep step

Missing any of these makes the cell voltage value unreproducible. If the paper
omits a field, record it as `unknown`, never silently default it.
