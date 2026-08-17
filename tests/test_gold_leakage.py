"""T88 — keep the gold set's leakage inventory honest.

The ontology-extension evaluation (P4) is only meaningful if we know exactly which
of the human's proposed placements the agent could have simply read somewhere. That
inventory was measured once, by hand, on 2026-07-27. Without a guard it goes stale
the moment someone writes a new design note naming a gap and its parent.

This test re-measures. It scans every tracked text file for a gold gap's local name
co-occurring with its proposed parent label, and fails if a file is not already
accounted for — either as an accepted in-schema leak or in the gold file's
`leakage_inventory`.

It does NOT demand that leaks be removed. The leaking files are the project's
historical record (design doc, task cards, PROGRESS, supervisor reports) and editing
them to protect an evaluation would be falsifying the record. The correct response to
a failure is to add the file to `leakage_inventory` and exclude it from the eval
environment — the point is that the decision is made deliberately, not by omission.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

GOLD = Path("eval/gold/emmo_upstream_gold.yaml")

# The schema itself necessarily co-occurs: its functional related_mappings /
# close_mappings ARE the leak, which is why 7 of 10 placements are marked
# placement_blind: false. Generated artefacts inherit the same content.
ACCEPTED_IN_SCHEMA = {"schema/palimpsest.yaml"}

# .tex and .html are here because report/latex/ carries rendered twins of the .md
# reports. Omitting them made an entire directory of restated placements structurally
# invisible — including where the thesis chapters will land.
_TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".py", ".txt", ".toml", ".json", ".ttl",
                  ".tex", ".html"}


def _tracked_text_files() -> list[Path]:
    # --others --exclude-standard includes files not yet committed. Without it the
    # scan gives a false green on exactly the files someone is adding right now,
    # and only fails after the commit that introduced the leak.
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    return [
        Path(f) for f in out
        if Path(f).suffix in _TEXT_SUFFIXES
        and not f.startswith(("eval/", "schema/generated/", "tests/test_gold_leakage"))
    ]


@pytest.fixture(scope="module")
def gold() -> dict:
    return yaml.safe_load(GOLD.read_text())


def test_gold_is_sealed_and_self_consistent(gold):
    """The counts in meta must match the per-gap annotations."""
    gaps = gold["gaps"]
    meta = gold["meta"]
    assert len(gaps) == meta["n_unique_gaps"] == 10
    counts = {"true": 0, "false": 0, "unstated": 0}
    for g in gaps:
        counts[str(g["placement_blind"]).lower()] += 1
    assert counts["true"] == meta["n_placement_blind"]
    assert counts["false"] == meta["n_placement_leaked"]
    assert counts["unstated"] == meta["n_placement_unstated"]


def test_markers_are_gone_from_the_schema():
    """The excision must not be quietly reverted by a later schema edit."""
    assert "TODO_EMMO_UPSTREAM" not in Path("schema/palimpsest.yaml").read_text()


def _answer_iris(gold: dict) -> list[tuple[str, str]]:
    """The IRIs that ARE the answer for the two non-`open` gaps.

    These leak independently of any parent label, which is how the first version of
    this scan missed the ontology-extension skill quoting `closed_by_iri` verbatim.
    A gap whose `proposed_parent_label` is "(unstated)" is skipped by the pair scan
    entirely, so without this it has no guard at all.

    Scanning only the two "answer" IRIs left the placement IRIs unguarded, and those
    leak the same way: an IRI-to-label lookup table states a parent without ever typing
    the gap's own name, so the pair scan cannot fire either.
    """
    out = []
    for g in gold["gaps"]:
        for field in ("closed_by_iri", "false_friend_iri",
                      "proposed_parent_iri", "proposed_parent_iri_alt",
                      "proposed_sibling_iri"):
            if g.get(field):
                out.append((g["id"], g[field].split("#")[-1]))
    return out


def test_leakage_inventory_covers_every_leaking_file(gold):
    """No file may reveal a gold placement or answer without being inventoried."""
    known = ACCEPTED_IN_SCHEMA | {e["path"] for e in gold["meta"]["leakage_inventory"]}
    pairs = [
        (g["local_name"], g["proposed_parent_label"])
        for g in gold["gaps"]
        if g.get("proposed_parent_label") and not g["proposed_parent_label"].startswith("(")
    ]
    answers = _answer_iris(gold)

    found: dict[str, list[str]] = {}
    for path in _tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        hits = [
            f"{name}->{parent}"
            for name, parent in pairs
            # a parent label may be written as "Acidic / AlkalineElectrolyte"
            if name in text and any(p.strip() in text for p in parent.split("/"))
        ]
        hits += [f"{gid}:answer-iri" for gid, frag in answers if frag in text]
        if hits:
            found[str(path)] = hits

    uninventoried = {p: h for p, h in found.items() if p not in known}
    assert not uninventoried, (
        "these files reveal a gold placement but are not in leakage_inventory:\n"
        + "\n".join(f"  {p}: {', '.join(h)}" for p, h in sorted(uninventoried.items()))
        + f"\n\nAdd them to {GOLD} under meta.leakage_inventory (and exclude them from "
        "the eval environment). Do not delete the content — it is the project record."
    )


def test_scan_actually_catches_a_synthetic_leak(gold, tmp_path, monkeypatch):
    """Negative control: prove the scan fails on a planted leak.

    Without this, a scan that silently matched nothing would pass forever and read
    as evidence of no leakage.
    """
    planted = tmp_path / "leak.md"
    g = next(x for x in gold["gaps"] if x.get("closed_by_iri"))
    planted.write_text(f"The answer is {g['closed_by_iri']}\n")
    monkeypatch.setattr(
        "tests.test_gold_leakage._tracked_text_files", lambda: [planted]
    )
    with pytest.raises(AssertionError, match="answer-iri"):
        test_leakage_inventory_covers_every_leaking_file(gold)
