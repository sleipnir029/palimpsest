"""T74 — gold-thinness audit: are the false positives hallucinations, or real values
the gold omits? (€0, reads the extraction cache.)

T72/T74 precision is dragged down by 406 grid-wide FPs (predictions matching no gold).
A FP is EITHER a hallucination (model error → genuine precision loss) OR a real
measurement the hand-built gold simply doesn't list (gold-thinness → NOT a model
error, and the precision number understates the model). The two are separable by
CROSS-MODEL AGREEMENT: a value many INDEPENDENT models extract but gold lacks is
almost certainly real; a value one model emits once is likely a hallucination.

For every cached cell we recompute which predictions are FPs (greedy match against
gold, same as the scorer), then group FP (type, value) and count how many DISTINCT
models produced each. High agreement → candidate gold addition.

Run:  pixi run python experiments/gold_thinness.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ab_extract import GOLD, _matches

_EXTRACTIONS = Path(__file__).resolve().parent / "results" / "extractions"
_OUT = Path(__file__).resolve().parent / "results" / "gold_thinness.json"


def _false_positives(preds: list[tuple], gold: list) -> list[tuple]:
    """Predictions left over after the scorer's greedy type+tolerance match = FPs."""
    matched: set[int] = set()
    fps: list[tuple] = []
    for pt, pv in preds:
        hit = False
        for gi, (gt, gv) in enumerate(gold):
            if gi not in matched and _matches(pt, pv, gt, gv):
                matched.add(gi); hit = True; break
        if not hit:
            fps.append((pt, pv))
    return fps


def build() -> dict:
    # (type, rounded value) -> {sha8 -> set(model labels)} so we count DISTINCT models
    # per paper (a value is "agreed" if several independent models extract it there).
    agree: dict = defaultdict(lambda: defaultdict(set))
    for f in sorted(_EXTRACTIONS.glob("*.json")):
        payload = json.loads(f.read_text(encoding="utf-8"))
        sha = payload["paper_sha"]
        gold = GOLD.get(sha)
        if gold is None:
            continue
        preds = [(it.get("type"), it.get("value")) for it in payload["items"]]
        for pt, pv in _false_positives(preds, gold):
            if pv is None:
                continue
            agree[(pt, round(float(pv), 3))][sha[:8]].add(payload["label"])

    rows = []
    for (typ, val), per_paper in agree.items():
        # max distinct models agreeing on this FP value within a single paper
        best_sha, best_models = max(per_paper.items(), key=lambda kv: len(kv[1]))
        rows.append({
            "type": typ, "value": val, "sha8": best_sha,
            "n_models_agree": len(best_models),
            "models": sorted(best_models),
        })
    rows.sort(key=lambda r: r["n_models_agree"], reverse=True)
    return {"candidates": rows}


def _print(rows: list[dict]) -> None:
    likely_real = [r for r in rows if r["n_models_agree"] >= 3]
    hallucinated = [r for r in rows if r["n_models_agree"] == 1]
    print("\nGOLD-THINNESS AUDIT — false positives by cross-model agreement\n")
    print(f"  distinct FP (type,value,paper) groups : {len(rows)}")
    print(f"  likely REAL (>=3 models agree)         : {len(likely_real)}  "
          f"← candidate gold additions, NOT model errors")
    print(f"  ambiguous (2 models)                   : "
          f"{len([r for r in rows if r['n_models_agree'] == 2])}")
    print(f"  likely hallucination (1 model only)    : {len(hallucinated)}")
    print("\nTOP candidate gold additions (>=3 models extracted it, gold lacks it):\n")
    print(f"  {'type':18} {'value':>10} {'paper':>9} {'#models':>8}")
    for r in likely_real[:25]:
        print(f"  {r['type']:18} {r['value']:>10} {r['sha8']:>9} {r['n_models_agree']:>8}")


def main() -> None:
    if not _EXTRACTIONS.exists():
        print("no extractions cached — run llm_matrix_t74.py first.", file=sys.stderr)
        return
    data = build()
    _OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _print(data["candidates"])
    print(f"\nwrote {_OUT}")


if __name__ == "__main__":
    main()
