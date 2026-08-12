"""T86 — guard the mined convention tiers.

The gate (T91) reads these tiers instead of re-deriving rules from prose, so a silent
shift here silently changes what the gate rejects. Two things are worth pinning: the
tier policy's boundaries, and the fact that the five structural ECHO predicates really
do come out REQUIRED against the pinned artefact.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))

from ontology_conventions import (  # noqa: E402
    REQUIRED_AT,
    WARN_AT,
    classify_rule,
    echo_report,
    h2kg_report,
)


@pytest.mark.parametrize(
    "rate,expected",
    [
        (1.0, "REQUIRED"),
        (REQUIRED_AT, "REQUIRED"),      # boundary is inclusive
        (REQUIRED_AT - 1e-9, "WARN"),
        (WARN_AT, "WARN"),              # boundary is inclusive
        (WARN_AT - 1e-9, "IGNORE"),
        (0.0, "IGNORE"),
    ],
)
def test_tier_boundaries(rate, expected):
    assert classify_rule(rate) == expected


@pytest.mark.slow
def test_echo_structural_predicates_are_required():
    """The five predicates every ECHO-local class carries must land in REQUIRED.

    If the pin moves and one of these drops below 85%, the gate would quietly stop
    demanding it — so fail here instead.
    """
    r = echo_report()
    tiers = {n: classify_rule(v) for n, v in r["rates_local"].items()}
    for name in ("skos:prefLabel", "rdfs:label", "elucidation",
                 "rdfs:subClassOf", "<any description>"):
        assert tiers[name] == "REQUIRED", f"{name} fell to {tiers[name]}"

    # Measured, not assumed: ECHO does NOT require an external definition source,
    # contrary to its own prose docs. This pins the finding.
    assert tiers["<any definition source>"] == "IGNORE"
    assert r["n_classes_local"] < r["n_classes_merged"], (
        "ECHO's TTL is a merged closure; the local subset is the right denominator"
    )


@pytest.mark.slow
def test_h2kg_quantity_value_is_type_dependent():
    """hasQuantityValue is REQUIRED for Parameter/Property and IGNOREd elsewhere.

    A flat rule would be wrong in both directions; per-type rates give the correct
    answer with no special-casing.
    """
    tiers = {
        t: {p: classify_rule(v) for p, v in row.items() if p != "n"}
        for t, row in h2kg_report()["rates_by_type"].items()
    }
    assert tiers["Parameter"]["h2kg:hasQuantityValue"] == "REQUIRED"
    assert tiers["Property"]["h2kg:hasQuantityValue"] == "REQUIRED"
    assert tiers["Matter"]["h2kg:hasQuantityValue"] == "IGNORE"
    assert tiers["Instrument"]["h2kg:hasQuantityValue"] == "IGNORE"


@pytest.mark.slow
def test_h2kg_alignment_is_negligible():
    """Pins the headline structural finding: H2KG imports nothing and maps almost nothing."""
    r = h2kg_report()
    assert r["n_owl_imports"] == 0
    assert r["n_restrictions"] == 0
    # denominator is the real term count, not the raw individual count — a third of
    # those are `file:///…` stubs the ODK build emitted.
    assert r["n_skos_mappings"] / r["n_individuals_h2kg_ns"] < 0.01
    assert r["n_individuals_h2kg_ns"] < r["n_individuals"]


def test_emitted_json_is_strict_json():
    """The gate consumes this file. `float('nan')` serialises to bare NaN, which is a
    Python extension and not JSON — anything stricter than Python's own parser breaks."""
    out = Path("experiments/results/ontology_conventions.json")
    if not out.exists():
        pytest.skip("run experiments/ontology_conventions.py first")

    def _reject(const):
        raise AssertionError(f"non-JSON constant {const!r} in {out}")

    data = json.loads(out.read_text(), parse_constant=_reject)
    # and the keys the gate is promised
    assert set(data) == {"echo", "h2kg"}
    for key in ("tiers", "rates_local", "n_classes_local",
                "n_restrictions_local", "n_restrictions_merged"):
        assert key in data["echo"], key
    for key in ("tiers_by_type", "rates_by_type", "n_individuals_h2kg_ns"):
        assert key in data["h2kg"], key


_SKILL_DIR = Path("skills/general/ontology-extension")


@pytest.mark.parametrize(
    "doc,claim,path,expected",
    [
        ("SKILL.md", "ECHO-local class count", ("echo", "n_classes_local"), "927"),
        ("SKILL.md", "H2KG real term count", ("h2kg", "n_individuals_h2kg_ns"), "2,176"),
        ("references/echo-conventions.md", "ECHO-local class count",
         ("echo", "n_classes_local"), "927"),
        ("references/h2kg-term-shape.md", "H2KG real term count",
         ("h2kg", "n_individuals_h2kg_ns"), "2,176"),
    ],
)
def test_skill_quotes_match_measured_json(doc, claim, path, expected):
    """The skill opens by claiming every rule was measured. Hold it to that.

    Catches the class of error where a number is written from the merged closure, from
    an older artefact, or from the ontology's own prose docs rather than from the JSON
    this repo actually produced.
    """
    out = Path("experiments/results/ontology_conventions.json")
    if not out.exists():
        pytest.skip("run experiments/ontology_conventions.py first")
    data = json.loads(out.read_text())
    measured = data[path[0]][path[1]]
    assert f"{measured:,}" == expected, (
        f"test fixture is stale: measured {claim} is now {measured:,}, not {expected}"
    )
    assert expected in (_SKILL_DIR / doc).read_text(), (
        f"{doc} does not quote the measured {claim} ({expected})"
    )
