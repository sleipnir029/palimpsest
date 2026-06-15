"""T52 — model A/B: deepseek-v4-flash vs deepseek-v4-pro on extraction recall/precision.

Scores each model's `extract()` output against the hand-built ground truth in
`experiments/ground_truth.md`. Run with `pixi run python experiments/ab_extract.py`.
Live (paid, ~€0.05-0.10); not a CI test.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root on path so the root-level `schema` namespace package resolves when this
# script is run directly (pixi run python experiments/ab_extract.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from palimpsest.cache import ParserCache
from palimpsest.cost import CostMeter
from palimpsest.providers import DeepSeekProvider
from palimpsest.tools.extract import extract

load_dotenv()

# Ground truth (type, value) — see experiments/ground_truth.md.
GT_MODELED = [  # representable by the current 7 Measurement classes (recall denominator for the A/B)
    ("Overpotential", 236.0), ("Overpotential", 298.0), ("Overpotential", 412.0), ("Overpotential", 511.0),
    ("TafelSlope", 52.6), ("TafelSlope", 75.8), ("TafelSlope", 109.8), ("TafelSlope", 131.3),
    ("MassActivity", 3343.37), ("MassActivity", 65.35),
    ("TurnoverFrequency", 1.665), ("TurnoverFrequency", 0.0237),
]
# T52 F3 landed: SpecificActivity + Stability are now modeled → folded into GT_MODELED above
# would make 19; kept separate here so the post-F3 recall delta is visible.
GT_F3 = [
    ("SpecificActivity", 0.098), ("SpecificActivity", 0.035), ("SpecificActivity", 0.01),
    ("Stability", 30.0), ("Stability", 15.0), ("Stability", 9.0), ("Stability", 6.0),
]
GT_MODELED = GT_MODELED + GT_F3  # 19 total now that F3 classes exist
GT_UNMODELED = []  # remaining gaps (R_ct, FE) are out of scope — see ground_truth.md


def _matches(pred_type, pred_val, gt_type, gt_val) -> bool:
    if pred_type != gt_type:
        return False
    tol = max(abs(gt_val) * 0.01, 0.5 if abs(gt_val) >= 1 else 1e-4)
    return abs(pred_val - gt_val) <= tol


def _score(valid, ground_truth):
    preds = [(type(v).__name__, v.value) for v in valid]
    matched = set()
    tp = 0
    for pt, pv in preds:
        for i, (gt, gv) in enumerate(ground_truth):
            if i not in matched and _matches(pt, pv, gt, gv):
                matched.add(i); tp += 1
                break
    recall = tp / len(ground_truth)
    precision = tp / len(preds) if preds else 0.0
    return tp, len(preds), recall, precision


def _pro_provider():
    p = DeepSeekProvider(model="deepseek-v4-pro")
    p.name = "deepseek-v4-pro"
    p.prices = {  # pro rates (api-docs.deepseek.com); flash class default is wrong for pro
        "input_tokens": 0.435 / 1_000_000, "output_tokens": 0.87 / 1_000_000,
        "cache_read_input_tokens": 0.435 / 1_000_000, "cache_creation_input_tokens": 0.435 / 1_000_000,
    }
    return p


def main() -> None:
    sha = sorted(Path("cache").glob("*/mineru.json"))[0].parent.name
    cache = ParserCache()
    models = [("flash", DeepSeekProvider()), ("pro", _pro_provider())]
    print(f"paper sha={sha[:12]} | GT modeled={len(GT_MODELED)} unmodeled(F3)={len(GT_UNMODELED)}\n")
    for label, provider in models:
        for run in range(2):
            meter = CostMeter(f"/tmp/ab_{label}_{run}.db")
            valid, errors = extract(paper_sha=sha, provider=provider, cost_meter=meter, cache=cache)
            tp, n, recall, prec = _score(valid, GT_MODELED)
            # how many of the (currently unrepresentable) F3 types did it try to emit?
            print(f"{label:5} run{run}: valid={n:2d} errors={len(errors):2d} "
                  f"TP={tp:2d}/{len(GT_MODELED)} recall={recall:.0%} precision={prec:.0%} "
                  f"spend=€{meter.total_eur():.4f}")


if __name__ == "__main__":
    main()
