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
patching schema/palimpsest.yaml to mark paper/page/bbox/parser_name as
`required: true`, the test pins the CLAUDE.md provenance non-negotiable into
the pydantic layer — Evidence() with missing required slots MUST fail.
"""

import json
from pathlib import Path

import pytest

GEN = Path(__file__).resolve().parent.parent / "schema" / "generated"
HEADER_TEXT = "DO NOT EDIT BY HAND. Run: pixi run schema"


def test_pydantic_import():
    from schema.generated.pydantic import Overpotential  # noqa: F401


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

    Schema marks these 4 slots required (T19 audit follow-up). Pydantic must
    reject Evidence instances missing any of them — silent acceptance would let
    T22 ship provenance-less triples into pyoxigraph.
    """
    from pydantic import ValidationError

    from schema.generated.pydantic import Evidence, Paper

    # Empty Evidence: all 4 required slots missing.
    with pytest.raises(ValidationError):
        Evidence()

    # Missing one required slot (parser_name): still rejected.
    with pytest.raises(ValidationError):
        Evidence(
            paper=Paper(sha256="deadbeef"),
            page=1,
            bbox=[0.0, 0.0, 1.0, 1.0],
        )

    # All 4 provenance slots present: succeeds; source_text stays optional.
    ev = Evidence(
        paper=Paper(sha256="deadbeef"),
        page=1,
        bbox=[0.0, 0.0, 1.0, 1.0],
        parser_name="docling",
    )
    assert ev.page == 1
    assert ev.parser_name == "docling"
    assert len(ev.bbox) == 4
    assert ev.source_text is None
