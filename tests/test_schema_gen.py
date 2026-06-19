"""T19 — schema generation pipeline.

Asserts the four `pixi run schema` artifacts exist and the most load-bearing
one (`pydantic.py`) imports + instantiates.

The card example writes `Overpotential(value=236.0, unit="qudt:MilliV", ...)`,
but the real schema slot is `unit_label` (Measurement.unit_label, free-text per
schema/palimpsest.yaml). Test uses the real slot name.

The header tests are the regen-safety canary the advisor flagged: if a future
`pixi run schema` overwrites a file without re-adding the "DO NOT EDIT" line,
the test fails loudly instead of silently shipping an un-marked artifact.

`test_evidence_requires_provenance_fields` is the T19-audit follow-up: after
patching schema/palimpsest.yaml to mark paper/page/bbox_{x0,y0,x1,y1}/parser_name
as `required: true`, the test pins the CLAUDE.md provenance non-negotiable into
the pydantic layer — Evidence() with missing required slots MUST fail. F4
(2026-06-08) split bbox into 4 typed per-corner slots; this test now exercises
all 4.
"""

import json
from pathlib import Path

import pytest

GEN = Path(__file__).resolve().parent.parent / "schema" / "generated"
HEADER_TEXT = "DO NOT EDIT BY HAND. Run: pixi run schema"


def test_pydantic_import():
    from schema.generated.pydantic import Overpotential  # noqa: F401


def test_f3_classes_generated():
    """T52: the two F3 classes regenerate into the Pydantic module."""
    from schema.generated.pydantic import SpecificActivity, Stability  # noqa: F401

    assert SpecificActivity(value=0.098, unit_label="mA/cm2").value == 0.098
    assert Stability(value=30.0, unit_label="h").value == 30.0


def test_t71_pemwe_classes_generated():
    """T71: the two PEMWE full-cell classes regenerate into the Pydantic module,
    and the new catalyst_loading Condition slot exists."""
    from schema.generated.pydantic import (  # noqa: F401
        Condition,
        DegradationRate,
        PEMWECellVoltage,
    )

    assert PEMWECellVoltage(value=1.75, unit_label="V").value == 1.75
    assert DegradationRate(value=0.022, unit_label="mV/h").value == 0.022
    assert Condition(catalyst_loading=0.15).catalyst_loading == 0.15


def test_pydantic_instantiation():
    from schema.generated.pydantic import Overpotential

    o = Overpotential(value=236.0, unit_label="mV")
    assert o.value == 236.0
    assert o.unit_label == "mV"


def test_shacl_nonempty():
    p = GEN / "shacl.ttl"
    assert p.stat().st_size > 0
    txt = p.read_text()
    assert "@prefix" in txt  # actual Turtle body, not header alone
    assert "sh:NodeShape" in txt


def test_pydantic_header_present():
    p = GEN / "pydantic.py"
    assert HEADER_TEXT in p.read_text().splitlines()[0]


def test_shacl_header_present():
    p = GEN / "shacl.ttl"
    assert HEADER_TEXT in p.read_text().splitlines()[0]


def test_jsonld_header_present():
    p = GEN / "context.jsonld"
    data = json.loads(p.read_text())
    assert data.get("_generated", "").startswith("DO NOT EDIT BY HAND")


def test_jsonschema_header_present():
    p = GEN / "jsonschema.json"
    data = json.loads(p.read_text())
    assert data.get("_generated", "").startswith("DO NOT EDIT BY HAND")


def test_evidence_requires_provenance_fields():
    """CLAUDE.md non-negotiable: every triple carries paper/page/bbox/parser_name.

    Schema marks 7 slots required (T19 audit + F4 split): paper, page,
    bbox_x0, bbox_y0, bbox_x1, bbox_y1, parser_name. Pydantic must reject
    Evidence instances missing any of them — silent acceptance would let T22
    ship provenance-less triples into pyoxigraph.
    """
    from pydantic import ValidationError

    from schema.generated.pydantic import Evidence, Paper

    # Empty Evidence: all required slots missing.
    with pytest.raises(ValidationError):
        Evidence()

    # Missing one required slot (parser_name): still rejected.
    with pytest.raises(ValidationError):
        Evidence(
            paper=Paper(sha256="deadbeef"),
            page=1,
            bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
        )

    # All required slots present: succeeds; source_text stays optional.
    ev = Evidence(
        paper=Paper(sha256="deadbeef"),
        page=1,
        bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
        parser_name="docling",
    )
    assert ev.page == 1
    assert ev.parser_name == "docling"
    assert (ev.bbox_x0, ev.bbox_y0, ev.bbox_x1, ev.bbox_y1) == (0.0, 0.0, 1.0, 1.0)
    assert ev.source_text is None


def test_paper_requires_sha256():
    """T15 cache-key contract + provenance non-negotiable.

    Without sha256 the Paper has no identity, and Evidence.paper (required by
    the T19 audit patch) would point at an identity-less object — that's the
    "paper_hash" half of CLAUDE.md's provenance triple. The audit caught the
    hole; the patch + this test close it.
    """
    from pydantic import ValidationError

    from schema.generated.pydantic import Paper

    # No sha256 → reject. doi/title/authors stay optional.
    with pytest.raises(ValidationError):
        Paper()

    p = Paper(sha256="deadbeef")
    assert p.sha256 == "deadbeef"
    assert p.doi is None
    assert p.title is None


# --- T47: H2KG skos alignment ---

H2KG_NS = "https://w3id.org/h2kg/hydrogen-ontology#"

# Each metric class → the H2KG term it close-matches. ECSA's H2KG fragment is the
# spelled-out name (altLabel "ECSA"), verified against ViMiLabs/AIMWORKS@main 2026-06-10.
H2KG_CLOSE_MAPPINGS = {
    "Overpotential": "h2kg:Overpotential",
    "TafelSlope": "h2kg:TafelSlope",
    "ExchangeCurrentDensity": "h2kg:ExchangeCurrentDensity",
    "ChargeTransferCoefficient": "h2kg:ChargeTransferCoefficient",
    "MassActivity": "h2kg:MassActivity",
    "TurnoverFrequency": "h2kg:TurnoverFrequency",
    "ECSA": "h2kg:ElectrochemicallyActiveSurfaceArea",
    # T71 — PEMWE full-cell classes (h2kg Property individuals, verified 2026-06-19).
    "PEMWECellVoltage": "h2kg:CellVoltage",
    "DegradationRate": "h2kg:CellVoltageIncreaseRate",
}


def test_h2kg_prefix_in_jsonld_context():
    """T47: the h2kg prefix resolves to the H2KG namespace in the generated context."""
    p = GEN / "context.jsonld"
    data = json.loads(p.read_text())
    assert data["@context"]["h2kg"] == H2KG_NS


def test_h2kg_close_mappings_on_classes():
    """T47: each metric class carries its expected h2kg: CURIE in close_mappings.

    context.jsonld only proves the prefix map; this parses the source schema to
    prove the mappings landed on the right classes, then confirms each CURIE
    survived regeneration into pydantic.py's linkml_meta (the one generated
    artifact that actually carries the feature) — so a regen that drops a
    mapping fails here, not silently.
    """
    import yaml

    schema = yaml.safe_load(
        (Path(__file__).resolve().parent.parent / "schema" / "palimpsest.yaml").read_text()
    )
    assert schema["prefixes"]["h2kg"] == H2KG_NS

    classes = schema["classes"]
    pydantic_src = (GEN / "pydantic.py").read_text()
    for cls, curie in H2KG_CLOSE_MAPPINGS.items():
        assert curie in classes[cls].get("close_mappings", []), (
            f"{cls} missing close_mapping {curie} in schema/palimpsest.yaml"
        )
        assert curie in pydantic_src, (
            f"{curie} missing from generated pydantic.py — stale regen?"
        )
