"""T23 — SHACL validation tests.

Three cases:
 1. Fully populated Overpotential → SHACL conforms.
 2. Evidence without ``parser_name`` (hand-crafted JSON-LD, since Pydantic
    would refuse to construct it after T19's required-fields audit) → SHACL
    rejects with ``sh:minCount 1`` on ``palimpsest:parserName``.
 3. Batch wrapper returns one row per input, in order.
"""

from __future__ import annotations

import json
from pathlib import Path

from schema.generated.pydantic import Condition, Evidence, Overpotential, Paper

from palimpsest.validation import (
    _validate_jsonld,
    validate_batch,
    validate_instance,
)


def _good_overpotential(value: float = 236.0) -> Overpotential:
    return Overpotential(
        value=value,
        unit_label="mV",
        condition=Condition(
            current_density=10.0,
            temperature_C=25.0,
        ),
        evidence=Evidence(
            paper=Paper(sha256="abc123", doi="10.1000/x"),
            page=3,
            bbox_x0=0.1, bbox_y0=0.2, bbox_x1=0.3, bbox_y1=0.4,
            parser_name="mineru",
        ),
    )


def test_valid_overpotential_passes():
    ok, report = validate_instance(_good_overpotential())
    assert ok, f"expected conforms; report:\n{report}"


def test_evidence_missing_parser_name_fails():
    """Reaches into the module-private ``_validate_jsonld`` because the public
    ``validate_instance(BaseModel)`` surface can't express this case — Pydantic
    refuses to construct an Evidence without ``parser_name`` (T19 required-fields
    audit). The SHACL-only catch must be exercised via the underlying helper.
    """
    ctx = json.loads(Path("schema/generated/context.jsonld").read_text())["@context"]
    bad = {
        "@context": ctx,
        "@type": "Evidence",
        "paper": {"@type": "Paper", "sha256": "abc"},
        "page": 3,
        "bbox_x0": 0.1, "bbox_y0": 0.2, "bbox_x1": 0.3, "bbox_y1": 0.4,
        # parser_name intentionally omitted
    }
    ok, report = _validate_jsonld(bad)
    assert not ok, f"expected SHACL violation; report:\n{report}"
    assert "parserName" in report, (
        f"expected report to mention parserName; got:\n{report}"
    )


def test_batch_preserves_order_and_results():
    a = _good_overpotential(value=236.0)
    b = _good_overpotential(value=298.0)
    results = validate_batch([a, b])
    assert len(results) == 2
    assert results[0][0] is a
    assert results[1][0] is b
    assert results[0][1] is True
    assert results[1][1] is True


def test_closed_shape_rejects_unknown_property():
    """``sh:closed=true`` on every shape rejects unknown predicates. Pydantic's
    ``extra="forbid"`` only fires at construction time; SHACL is the gate for
    any RDF that arrives by another path (e.g. JSON-LD from an external source
    or a future code path that bypasses the Pydantic models).
    """
    ctx = json.loads(Path("schema/generated/context.jsonld").read_text())["@context"]
    bad = {
        "@context": ctx,
        "@type": "Condition",
        "current_density": 10.0,
        # Unknown predicate routed via @vocab fallback to palimpsest:fictionalSlot,
        # which is not in the Condition shape's allowed-properties list.
        "fictional_slot": "nope",
    }
    ok, report = _validate_jsonld(bad)
    assert not ok, f"expected closed-shape violation; report:\n{report}"


# Note: a meaningful `validate_batch` mixed-pass/fail test requires a
# Pydantic-valid + SHACL-fail input. The current schema has none — every
# SHACL `sh:minCount 1` slot is also a Pydantic required field, so any
# SHACL-fail item is rejected by Pydantic at construction. (F4 closed
# the previous Pydantic-valid + SHACL-fail bbox-dedup gap by splitting
# bbox into 4 typed slots; no replacement input has surfaced.) Add a
# real mixed-batch test here if T24 introduces an external JSON-LD path
# that bypasses Pydantic.
