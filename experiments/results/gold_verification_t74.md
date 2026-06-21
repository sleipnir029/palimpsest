# T74 — gold-candidate verification (against parsed text)

Adjudication of the ≥3-model gold-thinness candidates (`gold_candidates_t74.md`)
against the cited parser spans. **Verifies what the parser surfaced; the PDF is the
final authority for rows marked UNCERTAIN.** Verdicts: ✅ add to GOLD · ⚠️ real value
but needs a fix before adding · ❌ reject · ❓ needs PDF.

## ✅ Confirmed REAL — parser text explicitly states it, correct quantity
| paper | type | value | evidence |
|---|---|---|---|
| bd9811a5 | PEMWECellVoltage | 1.939, 1.986, 2.000 V | "voltage initially rose from **1.939 V to 2.000 V** in the first 500 h … reached **1.986 V** when … stopped at 1,600 h" |
| c9a68107 | PEMWECellVoltage | 1.67, 1.83 V | "**1.67V** i@ 1 A/cm²", "**1.83V** i@ 2 A/cm²" (+ "cell potential of 2.0 V") |
| bd9811a5 | Stability | 1000 h | "degradation … over **1,000 h**" |
| c6319397 | Stability | 400 h | "operational stability … **over 400 h** at both 1 A/cm² and 2 A/cm²" |

## ⚠️ REAL value, WRONG number — unit mislabel (must fix before adding)
The models emitted µV/h readings under an `mV/h` label WITHOUT converting, so the
stored value is **1000× too large**. C2 passed because the *label* matched the
canonical unit — it does not check the value was actually converted.
| paper | type | model value (mV/h) | paper says | corrected (mV/h) |
|---|---|---|---|---|
| c6319397 | DegradationRate | 22, 52 | "22 µV/h", "≈52 µV/h @ 2 A/cm²" | 0.022, 0.052 |
| bd9811a5 | DegradationRate | 2.3, 2.8 | "2.3–2.8 µV h⁻¹ over the 1,500-h test" | 0.0023, 0.0028 |

## ❌ Reject — wrong quantity, artifact, or already in GOLD
| paper | type | value | why reject |
|---|---|---|---|
| c6319397 | Overpotential | 294, 324, 6, 12 | **cell-level kinetic / EIS-deconvolved overpotential at 2 A/cm²**, NOT the three-electrode OER catalyst overpotential the class means (7 models agreed — wrong KIND) |
| bd86866b | Stability | 2.5 | the **measurement-window note** the gold-audit deliberately removed ("stable for 20 cycles and 2.5 h of operation") — reconfirmed |
| c9a68107 | PEMWECellVoltage | 1.9 | misread of **1.9 A/cm² current density** as a voltage |
| 3432d049 | Stability | 2.0 | artifact — text states 30 h stability; the "2" is the **cm⁻² exponent** (8 models agreed — shared parser artifact) |
| bd9811a5 | Stability | 20 | artifact from the XAS coordination-shell span (Å distances) |
| 3432d049 | Overpotential / TOF | 236, 412, 1.665 | already in GOLD (duplicate extractions) |
| c9a68107 / bd9811a5 | Stability | 120, 1500 | already in GOLD |

## ❓ Uncertain — needs the PDF / figure
c6319397 Overpotential 260 (three-electrode? not in docling text) · c6319397
PEMWECellVoltage 1.79 · c6319397 DegradationRate 460 (which test?) · bd86866b
Overpotential 220 · bd86866b TOF 0.001/0.01 (figure) · 3432d049 TOF 0.013 ·
c9a68107 SpecificActivity 5.2.

## Meta-findings
1. **High agreement ≠ correct.** The single highest-agreement candidate (8 models,
   Stability=2.0) is a parser artifact, and a 7-model candidate (Overpotential
   294/324) is the wrong quantity. Cross-model agreement reliably surfaces
   gold-thinness but ALSO amplifies shared parser artifacts and semantic
   mis-classifications — verification is mandatory; agreement is a filter, not a
   verdict. Validates "propose, not auto-add".
2. **Unit-label gate gap (real bug).** C2/`units_match` validates the unit *label's
   dimension*, not that the value was converted to it. A model can emit a µV/h number
   under an `mV/h` label and pass, leaving the value 1000× off (every DegradationRate
   candidate). Fix needs a per-slot magnitude/range sanity check or re-deriving the
   value from the cited span's own unit string.
3. **Gold-audit reconfirmed** independently from the parsed text (Stability 2.5 stays out).

## Net
Of 32 ≥3-agreement candidates: ~6 clean adds (PEMWE cell voltages + two stabilities),
~4 real-but-unit-broken (DegradationRate, ÷1000), ~12 rejects, rest need the PDF. The
"32 gold-thinness" headline shrinks to a handful of clean additions — concentrated in
the **PEMWE full-cell metrics** the original three-electrode OER gold under-scoped (the
T71 domain). Verification, not agreement, is what separates them.
