"""T72 — per-tuple re-scorer + scorer audit, run over the extraction cache (€0).

The matrix CSV records only aggregate `tp`/`recall`. This re-scores the PERSISTED
extractions (`results/extractions/*.json`) tuple-by-tuple and classifies every gold
tuple into one of four outcomes, decomposing the single recall number into its causes:

  hit          — a prediction of the RIGHT type matched within tolerance (= official tp)
  wrong_type   — the value was extracted within tolerance but under the WRONG class name
                 (a scorer artifact: right number, sibling label → counted as a miss)
  coverage_gap — the value is not in this parser's text at all (no model could find it;
                 a parser-coverage ceiling — cross-referenced from coverage.json)
  model_gap    — the value IS in the parse but the model did not extract it (a true miss)

It also counts `fp` (predictions matching no gold — hallucination OR gold-incompleteness).

SCORER ARTIFACTS this exposes (the audit, in code):
  - TYPE is matched by exact class name (`type(v).__name__ == gt_type`), so a correct
    value under a sibling class scores 0 → the `wrong_type` bucket measures how often.
  - matching is GREEDY first-unmatched, so among same-type same-value gold the assignment
    is arbitrary (doesn't change the count, can mislabel which tuple).
  - precision's denominator is n_preds, so gold-thinness (real values gold omits) shows up
    as `fp` and understates precision — not a model error.

Run (after the matrix has populated the cache):  pixi run python experiments/rescore.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ab_extract import GOLD, _matches

_EXTRACTIONS = Path(__file__).resolve().parent / "results" / "extractions"
_COVERAGE = Path(__file__).resolve().parent / "results" / "coverage.json"
_OUT = Path(__file__).resolve().parent / "results" / "rescore.json"


def _tol(gt: float) -> float:
    return max(abs(gt) * 0.01, 0.5 if abs(gt) >= 1 else 1e-4)


def _load_coverage() -> dict:
    """{(parser, sha): [present_bool, ...] in GOLD order}, or {} if not built yet."""
    if not _COVERAGE.exists():
        return {}
    raw = json.loads(_COVERAGE.read_text(encoding="utf-8"))
    out: dict = {}
    for parser, papers in raw.items():
        for sha, e in papers.items():
            if e.get("cached"):
                out[(parser, sha)] = [t["present"] for t in e["tuples"]]
    return out


def classify(items: list[dict], gold: list, present: list[bool] | None) -> dict:
    """Per-tuple outcome for one cell. `present[i]` = gold[i]'s value is in the parse."""
    preds = [(it.get("type"), it.get("value")) for it in items]
    matched_gold: set[int] = set()
    used_pred: set[int] = set()

    # Step 1 — official greedy type+tolerance match (reproduces ab_extract._score tp).
    for pi, (pt, pv) in enumerate(preds):
        for gi, (gt, gv) in enumerate(gold):
            if gi in matched_gold:
                continue
            if _matches(pt, pv, gt, gv):
                matched_gold.add(gi)
                used_pred.add(pi)
                break

    # Step 2 — for still-unmatched gold, did SOME unused pred carry the value under the
    # wrong class name? (right number, wrong label → the scorer's type-strictness bites.)
    wrong_type: dict[int, str] = {}
    for gi, (gt, gv) in enumerate(gold):
        if gi in matched_gold or gv is None:
            continue
        if present is not None and not present[gi]:
            continue  # absent from the parse → coverage_gap, never wrong_type (N2)
        for pi, (pt, pv) in enumerate(preds):
            if pi in used_pred or pv is None:
                continue
            if abs(pv - gv) <= _tol(gv):
                wrong_type[gi] = pt
                used_pred.add(pi)
                break

    per_tuple = []
    buckets = {"hit": 0, "wrong_type": 0, "coverage_gap": 0, "model_gap": 0}
    for gi, (gt, gv) in enumerate(gold):
        if gi in matched_gold:
            status = "hit"
        elif gi in wrong_type:
            status = "wrong_type"
        elif present is not None and not present[gi]:
            status = "coverage_gap"
        else:
            status = "model_gap"  # present (or coverage unknown) but not extracted
        buckets[status] += 1
        rec = {"type": gt, "value": gv, "status": status}
        if status == "wrong_type":
            rec["predicted_as"] = wrong_type[gi]
        per_tuple.append(rec)

    fp = len(preds) - len(used_pred)  # preds matching no gold (hallucination OR gold gap)
    return {"n_preds": len(preds), "fp": fp, **buckets, "per_tuple": per_tuple}


def build() -> dict:
    cov = _load_coverage()
    cells = []
    for f in sorted(_EXTRACTIONS.glob("*.json")):
        payload = json.loads(f.read_text(encoding="utf-8"))
        sha = payload["paper_sha"]
        gold = GOLD.get(sha)
        if gold is None:
            continue
        present = cov.get((payload["parser"], sha))
        c = classify(payload["items"], gold, present)
        cells.append({
            "parser": payload["parser"], "label": payload["label"],
            "mode": payload["mode"], "sha8": sha[:8], "gt_total": len(gold),
            **c,
        })
    return {"cells": cells}


def _aggregate(cells: list[dict], mode: str = "raw") -> dict:
    """Sum buckets per (parser, label) for one mode."""
    agg: dict = defaultdict(lambda: {k: 0 for k in
                ("hit", "wrong_type", "coverage_gap", "model_gap", "fp", "gt_total", "n_preds")})
    for c in cells:
        if c["mode"] != mode:
            continue
        a = agg[(c["parser"], c["label"])]
        for k in a:
            a[k] += c[k]
    return agg


def _print(cells: list[dict]) -> None:
    agg = _aggregate(cells, "raw")
    print("\nPER-TUPLE TAXONOMY (raw mode) — where every gold tuple went\n")
    print(f"{'parser':9} {'model':16} {'hit':>4} {'wtyp':>5} {'cov':>4} {'mdl':>4} "
          f"{'fp':>4} {'recall':>7}")
    for (parser, label) in sorted(agg):
        a = agg[(parser, label)]
        gt = a["gt_total"] or 1
        print(f"{parser:9} {label:16} {a['hit']:4d} {a['wrong_type']:5d} "
              f"{a['coverage_gap']:4d} {a['model_gap']:4d} {a['fp']:4d} "
              f"{a['hit']/gt:6.0%}")
    # Totals — the decomposition of all misses across the grid.
    tot = {k: sum(a[k] for a in agg.values()) for k in
           ("hit", "wrong_type", "coverage_gap", "model_gap", "fp", "gt_total")}
    miss = tot["gt_total"] - tot["hit"]
    print(f"\nGRID TOTALS (raw): {tot['gt_total']} gold-slots, {tot['hit']} hits, "
          f"{miss} misses =")
    if miss:
        print(f"  coverage_gap (unreachable in parse) : {tot['coverage_gap']:4d} "
              f"({tot['coverage_gap']/miss:.0%} of misses)")
        print(f"  wrong_type   (scorer artifact)      : {tot['wrong_type']:4d} "
              f"({tot['wrong_type']/miss:.0%} of misses)")
        print(f"  model_gap    (true model miss)      : {tot['model_gap']:4d} "
              f"({tot['model_gap']/miss:.0%} of misses)")
    print(f"  false positives (incl. gold-thinness): {tot['fp']}")


def main() -> None:
    if not _EXTRACTIONS.exists() or not any(_EXTRACTIONS.glob("*.json")):
        print("no cached extractions yet — run llm_matrix.py first.", file=sys.stderr)
        return
    data = build()
    _OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _print(data["cells"])
    print(f"\nwrote {_OUT} ({len(data['cells'])} cells)")


if __name__ == "__main__":
    main()
