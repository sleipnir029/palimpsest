"""T86b — guard the category findings the supervisor write-up rests on.

Every claim here is about the shape of upstream ECHO, so every one of them can be
falsified by an upstream release. That is the point: if EMMO adds a disjointness axiom
separating quantities from roles, the "the gate cannot detect this" claim stops being
true and this suite should say so loudly rather than let the report keep asserting it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))

from ontology_categories import (  # noqa: E402
    CORRECT_PARENTS,
    EXPECTED_KIND,
    _by_label,
    analyse,
    ancestors,
    branches_of,
)

from palimpsest.ontology import echo_graph  # noqa: E402

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def graph():
    return echo_graph()


@pytest.fixture(scope="module")
def labels(graph):
    return _by_label(graph)


@pytest.fixture(scope="module")
def report():
    return analyse()


def test_electrocatalyst_is_a_role_not_a_quantity(graph, labels):
    """The finding the whole analysis turns on.

    ECHO's rdfs:comment calls it "material that can cause electrocatalysis", but the
    hierarchy puts it under Role. A quantity subclassed here is not mildly misfiled —
    it is asserted to be a role a material plays.
    """
    b = branches_of(graph, labels["Electrocatalyst"], labels)
    assert "role" in b
    assert "quantity" not in b
    anc = ancestors(graph, labels["Electrocatalyst"])
    assert labels["Role"] in anc
    assert labels["PhysicalQuantity"] not in anc


def test_quantities_reach_physicalquantity(graph, labels):
    """The other side of the same split — and the branch the gold never used."""
    for name in ("Overpotential", "ExchangeCurrentDensity", "ElectricPotential"):
        assert "quantity" in branches_of(graph, labels[name], labels), name


def test_no_disjointness_separates_quantity_from_role(report):
    """Why the reasoner half of ECHO's CI cannot catch the misplacement.

    If this ever fails, the report's "both halves of the gate pass it" claim is dead
    and §5.3 must be rewritten — which is a good outcome, not a broken test.
    """
    d = report["disjointness"]
    assert d["n_disjoint_pairs"] > 0, "closure carries no disjointness at all — check the pin"
    assert d["n_separating_quantity_from_role"] == 0, (
        f"upstream now separates the branches: {d['separating_pairs']}"
    )


def test_five_gold_placements_are_wrong_branch(report):
    """Pins the headline count quoted in the report and the gold header."""
    wrong = {r["id"] for r in report["gaps"] if r["verdict"] == "wrong-branch"}
    assert wrong == {
        "tafel-slope", "mass-activity", "turnover-frequency",
        "specific-activity", "stability",
    }


def test_oxygen_evolution_reaction_is_the_control(report):
    """The one gap whose hint points the right way.

    The trap benchmark needs it: an agent that rejects every schema hint fails here,
    so blanket scepticism is not a winning strategy.
    """
    row = next(r for r in report["gaps"] if r["id"] == "oxygen-evolution-reaction")
    assert row["verdict"] == "correct"
    assert row["expected_kind"] == "process"
    assert "process" in row["proposed_parent_branches"]


def test_corrected_parents_resolve_and_are_in_the_right_branch(graph, labels):
    """Each proposed fix must exist upstream and actually be a quantity.

    Guards against the failure this whole module is about: recommending a parent that
    reads plausibly but sits in the wrong branch.
    """
    for gap, (dimensional, domain) in CORRECT_PARENTS.items():
        for name in (dimensional, domain):
            assert name in labels, f"{gap}: {name!r} does not resolve in pinned ECHO"
            assert "quantity" in branches_of(graph, labels[name], labels), (
                f"{gap}: recommended parent {name!r} is not in the quantity branch"
            )


def test_specific_activity_label_is_unique_upstream(report):
    """So proposing a new ECHO class of that label fails emmocheck.test_unique_labels.

    The gold prescribes "decline the mapping and propose a new term"; that is
    incomplete, because the new term cannot carry this label.
    """
    fc = report["specific_activity_label_clash"]
    assert fc["n_classes_labelled_SpecificActivity"] == 1
    parents = next(iter(fc["parents"].values()))
    assert "AtomicAndNuclearPhysicsQuantity" in parents, (
        "the false friend is a radioactivity quantity; if this moves, re-check the case"
    )


def test_every_gap_with_a_parent_is_classified(report):
    """No gap should fall through unclassified — a missing EXPECTED_KIND would give a
    silent 'wrong-branch' verdict on a term nobody judged."""
    for row in report["gaps"]:
        if row["verdict"] == "no-parent-recorded":
            continue
        assert row["id"] in EXPECTED_KIND, f"{row['id']} has a parent but no expected kind"
        assert row["expected_kind"] is not None


def test_emitted_json_is_strict_json():
    out = Path("experiments/results/ontology_categories.json")
    if not out.exists():
        pytest.skip("run experiments/ontology_categories.py first")

    def _reject(const):
        raise AssertionError(f"non-JSON constant {const!r} in {out}")

    data = json.loads(out.read_text(), parse_constant=_reject)
    for key in ("gaps", "disjointness", "specific_activity_label_clash"):
        assert key in data, key
