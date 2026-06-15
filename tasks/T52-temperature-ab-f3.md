# T52 — temperature=0, model A/B vs ground truth, close T18a F3

## Why
DeepSeek extraction (T51) was correct but its yield wobbled (11–13) and we had no objective
baseline to judge "good" or to compare models. Three levers: make it deterministic, measure it
against a hand-built ground truth, and capture the measurement types the schema couldn't hold.

## What changed
- **temperature=0** in `DeepSeekProvider.extra_request` — reduce sampling variance (feeds a thesis
  metric). Default was 1.0 (max random); temp=0 removes the wild swing but is **not** deterministic
  (DeepSeek MoE still varies modestly — flash yield ranged 16-20 across runs; pro is steadiest).
- **Ground truth** (`experiments/ground_truth.md`) — human reading of the cached paper PDF:
  12 schema-modeled measurements + 7 then-unmodeled (SpecificActivity ×3, Stability ×4) + out-of-
  scope R_ct/FE. The denominator for recall.
- **A/B harness** (`experiments/ab_extract.py`) — scores flash vs pro (temp=0) vs ground truth.
- **Closed T18a F3 (ground-truth-driven):** added `SpecificActivity` (mA/cm2) + `Stability` (h)
  Measurement classes. NOT PEMWECellVoltage/SpecificECSA/Pressure (no paper reports them).

## Results (cached paper, temp=0)
- Pre-F3 (denom 12): flash 92% recall / 100% prec / €0.004; pro 100% / €0.013.
- Post-F3 (denom 19): **pro 100% recall both runs** / €0.027; flash 84–100% / €0.008.
- Closing the schema gap lifted achievable recall **12 → 19**.

## Recommendation
- **flash** for dev (cheap, stable, 92–100%); **pro** for final/thesis runs (steady 19/19 at
  €0.027/paper). Default left at flash — flip to pro in `extract.py`/`__main__.py` if wanted.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest -q     # 128 passed / 7 skipped, 0 failures
pixi run linkml-validate schema/palimpsest.yaml && pixi run schema   # clean
pixi run python experiments/ab_extract.py   # live A/B (paid)
```

## Open / future
- One paper cached; multi-paper A/B needs GPU parsing (cost).
- Still-unmodeled types: ChargeTransferResistance, Faradaic efficiency, PEMWECellVoltage,
  SpecificECSA, Pressure (T18a F3 remainder).
- Whether to make pro the default extraction model (cost vs recall) — user call.
