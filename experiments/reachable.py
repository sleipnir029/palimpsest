"""T74 — reachable-recall: recall normalized by the parser coverage ceiling (€0).

`recall = hit / gt_total` blames the model for gold tuples no model could reach
(absent from this parser's text). `reachable_recall = hit / (gt_total - coverage_gap)`
divides by what the parser ACTUALLY surfaced, isolating model skill from parser
limits — the T74/thesis axis. Established lineage: oracle-normalized recall /
Retriever Potential Attainment / SQuAD-2.0 answerable-subset recall.

Reads `results/rescore.json` (which already carries per-cell `hit`, `gt_total`,
`coverage_gap`), so this is pure post-hoc arithmetic — no model calls. Run
`rescore.py` first (it cross-refs `coverage.json`).

Run:  pixi run python experiments/reachable.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from multipass import reachable_recall

_RESCORE = Path(__file__).resolve().parent / "results" / "rescore.json"
_OUT = Path(__file__).resolve().parent / "results" / "reachable.json"


def build() -> dict:
    cells = json.loads(_RESCORE.read_text(encoding="utf-8"))["cells"]
    # Aggregate per (parser, label, mode): sum hits / gold / coverage_gap.
    agg: dict = defaultdict(lambda: {"hit": 0, "gt_total": 0, "coverage_gap": 0})
    for c in cells:
        a = agg[(c["parser"], c["label"], c["mode"])]
        a["hit"] += c["hit"]
        a["gt_total"] += c["gt_total"]
        a["coverage_gap"] += c["coverage_gap"]
    out = []
    for (parser, label, mode), a in sorted(agg.items()):
        out.append({
            "parser": parser, "label": label, "mode": mode,
            "hit": a["hit"], "gt_total": a["gt_total"], "coverage_gap": a["coverage_gap"],
            "recall": round(a["hit"] / a["gt_total"], 4) if a["gt_total"] else 0.0,
            "reachable_recall": round(
                reachable_recall(a["hit"], a["gt_total"], a["coverage_gap"]), 4),
        })
    return {"rows": out}


def _print(rows: list[dict]) -> None:
    print("\nREACHABLE-RECALL — recall ÷ parser ceiling (isolates model skill)\n")
    print(f"{'parser':9} {'model':16} {'mode':13} {'hit':>4} {'reach':>6} "
          f"{'recall':>7} {'reachable':>10}")
    for r in rows:
        print(f"{r['parser']:9} {r['label']:16} {r['mode']:13} {r['hit']:4d} "
              f"{r['gt_total'] - r['coverage_gap']:6d} {r['recall']:7.0%} "
              f"{r['reachable_recall']:10.0%}")


def main() -> None:
    if not _RESCORE.exists():
        print("no rescore.json — run coverage.py then rescore.py first.", file=sys.stderr)
        return
    data = build()
    _OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _print(data["rows"])
    print(f"\nwrote {_OUT} ({len(data['rows'])} rows)")


if __name__ == "__main__":
    main()
