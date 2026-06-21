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


# T72 — multi-paper gold for the breadth matrix. Keyed by the PDF's sha256 (= the
# `cache/<sha>/` dir name), so it works for ANY parser's cache. Papers 2-5 are
# transcribed from the 4-parser-consensus `experiments/ground_truth_<name>.md`
# files (T35); each tuple is a (Measurement-subclass-name, numeric value) the
# deterministic scorer can match.
# INCLUSION RULE: every consensus-table row that carries a NUMERIC value — including
# figure-derived numerics (e.g. the bd9811a5 Tafel slopes, read from Fig 3b). The only
# things dropped are rows with no number to match: qualitative durations ("tens of
# hours") and SI-only series not present in any parse. Rationale for keeping figure
# numerics: they ARE real measurements, and they're precisely where Stage 2 separates
# parsers (docling/paddle surface them, mineru does not).
# PARSER CAVEAT: the GT is parser-CONSENSUS, so on a single parser some rows are absent
# from that parser's text — they're unreachable by EVERY model there, deflating absolute
# recall uniformly (ranking stays valid; Stage 2 surfaces the gap). Concretely on Stage 1
# (mineru): bd9811a5's 4 figure-Tafel rows are docling+paddle-only, so its mineru recall
# ceiling is 4/8, not 8/8.
GOLD: dict[str, list[tuple[str, float]]] = {
    # s41467-022-35426-8 — Ir-Co3O4 (the original A/B paper); experiments/ground_truth.md
    "3432d04920eb6649d15d8883e64dc7f3d54700ecd5050d09e31ae286f1d4f53d": GT_MODELED,  # 19
    # s41467-023-40912-8 — IrO2@TaB2; ground_truth_s41467-023-40912-8.md (7)
    # T74 gold-thinness add (2026-06-21): 3 PEMWE full-cell voltages — Fig 5c labels
    # 1.67 V @1 A/cm² and 1.83 V @2 A/cm² (PDF-confirmed p7), text gives 2.0 V @3.06
    # A/cm². Under-scoped by the three-electrode OER gold. See results/gold_verification_t74.md.
    "c9a68107074a82259fe3fd9ba9061eec3956d563532a16e435175831f266e86c": [
        ("Overpotential", 288.0), ("Overpotential", 307.0),
        ("TafelSlope", 42.6), ("TafelSlope", 45.1),
        ("MassActivity", 345.0),
        ("Stability", 120.0), ("Stability", 40.0),
        ("PEMWECellVoltage", 1.67), ("PEMWECellVoltage", 1.83), ("PEMWECellVoltage", 2.0),
    ],
    # s41467-025-63541-9 — Ir/TiOx@Ti; ground_truth_s41467-025-63541-9.md (4)
    # T74 gold-thinness add (2026-06-21): Stability 400 h — "operational stability …
    # over 400 h at both 1 A/cm² and 2 A/cm²" (docling+dots). See gold_verification_t74.md.
    "c63193979cec7f3d44d6d989fab9f7a7ba60590b18545f9129a982e578b8dc17": [
        ("MassActivity", 192.0), ("MassActivity", 81.0),
        ("Stability", 1700.0), ("Stability", 40.0),
        ("Stability", 400.0),
    ],
    # s41565-025-02030-y — RuxIrOx; ground_truth_s41565-025-02030-y.md (8; row 9 RuO2
    # stability is qualitative "tens of hours" → no numeric tuple)
    # T74 gold-thinness add (2026-06-21): 3 PEMWE cell voltages from the durability hold —
    # "voltage initially rose from 1.939 V to 2.000 V in the first 500 h … reached 1.986 V
    # when … stopped at 1,600 h" (docling+paddle identical). See gold_verification_t74.md.
    "bd9811a577ff2ec3d6e9eee65c9edf954d0e5059f5470835ed4c498f4cc22a54": [
        ("Overpotential", 240.0),
        ("TafelSlope", 45.16), ("TafelSlope", 46.25),
        ("TafelSlope", 48.29), ("TafelSlope", 51.78),
        ("Stability", 1500.0), ("Stability", 1600.0), ("Stability", 200.0),
        ("PEMWECellVoltage", 1.939), ("PEMWECellVoltage", 1.986), ("PEMWECellVoltage", 2.0),
    ],
    # s41929-024-01168-7 — amorphous IrOx vs rutile IrO2; ground_truth_s41929-024-01168-7.md (2)
    # T72 gold-audit fix (2026-06-21): dropped ("Stability", 2.5). The paper's "2.5 h" is a
    # measurement-WINDOW reproducibility note for BOTH samples ("redox features ... stable for
    # 20 cycles and 2.5 h of operation"), NOT a durability/endurance benchmark — numerically
    # real but semantically not a Stability measurement. See results/gold_audit.md (paper 5).
    "bd86866b0d0ed41bd5cbaf523aa92287194f052841092df665df5380c303be01": [
        ("Overpotential", 210.0), ("Overpotential", 330.0),
    ],
}


def _matches(pred_type, pred_val, gt_type, gt_val) -> bool:
    if pred_type != gt_type:
        return False
    if pred_val is None:  # `value` is schema-nullable; a null-value extraction can't
        return False      # match a numeric gold (and must not crash the scorer)
    tol = max(abs(gt_val) * 0.01, 0.5 if abs(gt_val) >= 1 else 1e-4)
    return abs(pred_val - gt_val) <= tol


def _score_preds(preds, ground_truth):
    """Score a list of (type_name, value) prediction tuples against gold.

    Split out from `_score` so the same greedy matcher serves both the live path
    (Pydantic instances) and the cached path (T72 extraction cache → plain dicts),
    with no behaviour change for existing callers.
    """
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


def _score(valid, ground_truth):
    return _score_preds([(type(v).__name__, v.value) for v in valid], ground_truth)


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
    # Shared €50 ledger (NOT /tmp — that hid A/B spend from the cap). Per-run spend is
    # the ledger delta around each call; the budget gate sees all prior LLM+GPU spend.
    meter = CostMeter()
    models = [("flash", DeepSeekProvider()), ("pro", _pro_provider())]
    print(f"paper sha={sha[:12]} | GT modeled={len(GT_MODELED)} unmodeled(F3)={len(GT_UNMODELED)} "
          f"| ledger €{meter.total_eur():.2f}/€{meter.cap:.0f} before run\n")
    for label, provider in models:
        for run in range(2):
            meter.check_or_raise(0.20)  # €50 gate — refuse before spending
            before = meter.total_eur()
            valid, errors = extract(paper_sha=sha, provider=provider, cost_meter=meter, cache=cache)
            tp, n, recall, prec = _score(valid, GT_MODELED)
            # how many of the (currently unrepresentable) F3 types did it try to emit?
            print(f"{label:5} run{run}: valid={n:2d} errors={len(errors):2d} "
                  f"TP={tp:2d}/{len(GT_MODELED)} recall={recall:.0%} precision={prec:.0%} "
                  f"spend=€{meter.total_eur() - before:.4f}")
    print(f"\nledger now €{meter.total_eur():.2f}/€{meter.cap:.0f}")


if __name__ == "__main__":
    main()
