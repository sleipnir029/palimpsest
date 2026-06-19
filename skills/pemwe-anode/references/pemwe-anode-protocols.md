# PEMWE-anode single-cell / MEA protocols

PEMWE-anode papers test acidic-OER Ir/Ru catalysts at device scale, in a
membrane-electrode assembly (MEA). This reference covers the full-cell
conditions that gate `PEMWECellVoltage` and `DegradationRate`. (For the
three-electrode RDE conventions these papers also report, see the
`oer-extraction` references — they are reused unchanged.)

## Operating envelope

- **Temperature**: 75–80 °C (cell body / endplate); 60 °C sometimes used for
  stability tests. Record on `condition.temperature_C`.
- **Feed**: deionized water (≥ 1 MΩ cm, often ≥ 18 MΩ cm) to the anode, 1–50
  mL min⁻¹. Most labs feed the anode only.
- **Membrane**: Nafion 117 (~178 µm, durability), Nafion 115 (~127 µm), Nafion
  212 (~50 µm, performance). Reinforced membranes (Aquivion, Gore) in recent
  work. Record the membrane identity verbatim in `condition.cell_type`.
- **Anode catalyst loading**: Ir-based, 0.1–2 mg cm⁻² Ir; low-loading
  (≤ 0.4 mg cm⁻² Ir) is the cost headline. Record on
  `condition.catalyst_loading` (mg/cm²).
- **Cathode**: Pt/C, 0.1–0.5 mg cm⁻² Pt.
- **Porous transport layer (anode)**: Pt- or Au-coated Ti felt / sintered Ti.

## Cell voltage (`PEMWECellVoltage`, canonical V)

- Reported at a **cell** current density (A cm⁻²), current-controlled
  (galvanostatic staircase) or potential-controlled (slow LSV, 1–10 mV s⁻¹).
- Community points: Vcell @ 1 A cm⁻² (entry), Vcell @ 2 A cm⁻² (SOA target
  ≤ 1.75 V). Some papers instead report j @ a fixed Vcell (e.g. j @ 1.8 V) —
  that is a current density, not a `PEMWECellVoltage`.
- Steady-state holds of 60–300 s per step give an accurate Vcell.
- Almost always **iR-uncorrected**; record `iR_correction: unknown` unless the
  paper states a correction.

## Degradation rate (`DegradationRate`, canonical mV/h)

- Constant-current hold at 1–3 A cm⁻² for hundreds to thousands of hours; the
  degradation rate is the slope of Vcell vs time.
- Reported as **µV h⁻¹** (instantaneous) or **mV per 1000 h** (long campaigns).
  Convert to mV/h: 22 µV/h → 0.022 mV/h; 126 mV/1000 h → 0.126 mV/h.
- Always record the **hold current density** and **duration**; a 1 A cm⁻² rate
  and a 2 A cm⁻² rate are different claims.
- Accelerated stress tests (AST): OCV↔high-current cycling, square-wave holds,
  start/stop. Record the AST protocol if that is what produced the rate.

## What to record for every full-cell measurement

- cell current density (A cm⁻²) → `condition.current_density`
- temperature (°C) → `condition.temperature_C`
- anode loading (mg cm⁻² Ir) → `condition.catalyst_loading`
- membrane identity → `condition.cell_type`
- iR-correction status → `condition.iR_correction` (`unknown` if unstated)
- cell type family → `condition.cell_type_family` (`single_cell_MEA` / `stack`)

Missing the current density or temperature makes a cell voltage unreproducible.
If the paper omits a field, record it as `unknown`; never silently default it.
