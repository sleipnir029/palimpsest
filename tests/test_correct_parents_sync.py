"""The corrected parents are recorded twice, by hand: in the gold file's
`correct_parents` and in experiments/ontology_categories.py `CORRECT_PARENTS`
(the thesis's Table 7a cites both). Keep them equal."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))

from ontology_categories import CORRECT_PARENTS  # noqa: E402


def test_correct_parents_match_the_gold_file():
    gold = yaml.safe_load((ROOT / "eval/gold/emmo_upstream_gold.yaml").read_text(encoding="utf-8"))
    recorded = {g["id"]: (g["correct_parents"]["dimensional"], g["correct_parents"]["domain"])
                for g in gold["gaps"] if "correct_parents" in g}
    assert recorded == CORRECT_PARENTS


def test_emitted_json_matches_correct_parents():
    """experiments/results/ontology_categories.json is regenerated from CORRECT_PARENTS;
    a stale file would cite an old parent."""
    data = json.loads((ROOT / "experiments/results/ontology_categories.json").read_text(encoding="utf-8"))
    emitted = {}

    def walk(node):
        if isinstance(node, dict):
            cp = node.get("correct_parents")
            if isinstance(cp, dict) and "id" in node:
                emitted[node["id"]] = (cp["dimensional"], cp["domain"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    assert emitted == CORRECT_PARENTS
