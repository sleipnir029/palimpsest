# Ground truth — OER measurements (manual, authoritative)

Paper: **Ir-Co₃O₄ single atoms for acidic OER**, *Nat. Commun.* 13:7754 (2022),
DOI 10.1038/s41467-022-35426-8.
PDF: `papers/s41467-022-35426-8.pdf` · cache sha256 `3432d04920eb6649d15d8883e64dc7f3d54700ecd5050d09e31ae286f1d4f53d`.

Established by **human reading of the PDF** (pages 5–6, "Electrochemical performance"), NOT by an
LLM. This is the baseline for the model A/B (precision/recall) and the before/after-F3 comparison.

## Measurements

### Schema-modeled today (7 Measurement classes)
| # | type | catalyst | value | unit | conditions | pg |
|---|------|----------|-------|------|------------|----|
| 1 | Overpotential | Ir-Co₃O₄ | 236 | mV | @ 10 mA/cm², 0.5 M H₂SO₄, RDE/GCE | 5 |
| 2 | Overpotential | IrO₂ | 298 | mV | @ 10 mA/cm² | 5 |
| 3 | Overpotential | Co₃O₄ | 412 | mV | @ 10 mA/cm² | 5 |
| 4 | Overpotential | C-Co₃O₄ | 511 | mV | @ 10 mA/cm² | 5 |
| 5 | TafelSlope | Ir-Co₃O₄ | 52.6 | mV/dec | (±0.24) | 5 |
| 6 | TafelSlope | IrO₂ | 75.8 | mV/dec | (±0.25) | 5 |
| 7 | TafelSlope | Co₃O₄ | 109.8 | mV/dec | (±0.37) | 5 |
| 8 | TafelSlope | C-Co₃O₄ | 131.3 | mV/dec | (±0.23) | 5 |
| 9 | MassActivity | Ir-Co₃O₄ | 3343.37 | A/g_Ir | @ η=300 mV | 6 |
| 10 | MassActivity | IrO₂ | 65.35 | A/g_Ir | @ η=300 mV | 6 |
| 11 | TurnoverFrequency | Ir-Co₃O₄ | 1.665 | 1/s | @ η=300 mV, per geometric area/Ir sites | 5-6 |
| 12 | TurnoverFrequency | IrO₂ | 0.0237 | 1/s | @ η=300 mV | 6 |

**12 schema-representable measurements** → the recall denominator for the A/B (current schema).

### Present but NOT modeled until T18a F3 (this task adds the first two classes)
| # | type | catalyst | value | unit | conditions | pg |
|---|------|----------|-------|------|------------|----|
| 13 | SpecificActivity | Ir-Co₃O₄ | 0.098 | mA/cm²_ECSA | @ η=300 mV | 5 |
| 14 | SpecificActivity | IrO₂ | 0.035 | mA/cm²_ECSA | @ η=300 mV | 5 |
| 15 | SpecificActivity | Co₃O₄ | 0.01 | mA/cm²_ECSA | @ η=300 mV | 5 |
| 16 | Stability | Ir-Co₃O₄ | 30 | h | @ 10 mA/cm² (chronopotentiometry) | 6 |
| 17 | Stability | IrO₂ | 15 | h | @ 10 mA/cm² (before deactivating) | 6 |
| 18 | Stability | Co₃O₄ | 9 | h | @ 10 mA/cm² | 6 |
| 19 | Stability | Ir-Co₃O₄ | 6 | h | @ 50 mA/cm² | 6 |

→ After F3 adds **SpecificActivity + Stability**, the denominator becomes **19**.

### Present but OUT OF SCOPE (further schema gaps, not added here — noted for honesty)
- ChargeTransferResistance (R_ct, EIS): Ir-Co₃O₄ 2.37 Ω, IrO₂ 4.18 Ω, Co₃O₄ 20.55 Ω, C-Co₃O₄ 115.5 Ω (pg 6).
- Faradaic efficiency: ~100% (small η) → 97% (large η) (pg 6).
- ECSA / C_dl: described, no discrete number in main text (SI Fig 17).

## Matching rule for the A/B
A predicted measurement counts as a true positive if its `type` matches and its `value` is within
1% (or ±0.5 of small integers like stability hours) of a ground-truth row. Recall = TP / denominator
(12 pre-F3, 19 post-F3); precision = TP / predicted.
