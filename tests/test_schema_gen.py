"""T19 — schema generation pipeline.

Asserts the four `pixi run schema` artifacts exist and the most load-bearing
one (`pydantic.py`) imports + instantiates.

The card example writes `Overpotential(value=236.0, unit="qudt:MilliV", ...)`,
but the real schema slot is `unit_label` (Measurement.unit_label, free-text per
schema/palimpsest.yaml). Test uses the real slot name.

The header tests are the regen-safety canary the advisor flagged: if a future
`pixi run schema` overwrites a file without re-adding the "DO NOT EDIT" line,
the test fails loudly instead of silently shipping an un-marked artifact.
"""

import json
from pathlib import Path

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
