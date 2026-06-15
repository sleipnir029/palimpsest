"""T22/T51 — extraction tool tests.

T51: the LLM is shown numbered text spans PER PAGE and cites span ids; the runtime
resolves ids → bbox/page/source_text. Offline tests use a stub provider returning
canned JSON (the stub is called once per page; fixtures are single-page so there's
exactly one call). The cache is per-test (tmp_path).

Live test (`--live` only) hits real DeepSeek on a paper sha already cached by T16.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from pydantic import ValidationError

from palimpsest.cache import ParserCache
from palimpsest.cost import CostMeter
from palimpsest.providers.anthropic import LLMResponse
from palimpsest.tools.extract import (
    _dedup,
    _load_spans,
    _resolve_spans,
    _schema_for_prompt,
    extract,
)

load_dotenv()


# ----- fixtures -------------------------------------------------------------
# Single-page mineru geometry. Span ids are 0-based indices into the page.
SPAN_OVERP = "the overpotential was 236 mV at 10 mA cm-2"
SPAN_TAFEL = "the Tafel slope is 47 mV per decade"
SPAN_DISTRACT = "figure 2 shows the polarization trend"
BBOX_OVERP = (63.0, 137.0, 929.0, 244.0)
BBOX_TAFEL = (60.0, 250.0, 500.0, 270.0)


def _mineru_geometry() -> str:
    """One page (page_no 1) with 3 spans: [0] overpotential, [1] tafel, [2] distractor."""
    page = [
        {"type": "text", "content": SPAN_OVERP, "bbox": [63, 137, 929, 244]},
        {"type": "text", "content": SPAN_TAFEL, "bbox": [60, 250, 500, 270]},
        {"type": "text", "content": SPAN_DISTRACT, "bbox": [10, 300, 500, 360]},
    ]
    return json.dumps([page])


def _ev(*ids: int) -> dict:
    return {"spans": list(ids)}


def _seed_cache(
    tmp_path: Path,
    sha: str,
    parser_name: str = "mineru",
    parser_text: str | None = None,
    suffix: str = ".json",
) -> ParserCache:
    if parser_text is None:
        parser_text = _mineru_geometry()
    cache_dir = tmp_path / "cache"
    cache = ParserCache(db_path=str(tmp_path / "test.db"), cache_dir=cache_dir)
    cache.add_paper(sha256=sha, filename="x.pdf", page_count=12)
    rel = f"{sha}/{parser_name}{suffix}"
    out = cache_dir / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(parser_text)
    cache.insert_parser_run(
        sha256=sha, parser_name=parser_name, parser_ver="test",
        output_path=rel, gpu_seconds=0.0, gpu_cost_eur=0.0, run_id="r1",
    )
    return cache


class _StubProvider:
    """Returns a fixed LLMResponse for any input; called once per page."""

    name = "stub"

    def __init__(self, response_text: str) -> None:
        self._text = response_text
        self.calls = 0

    def complete(self, system, messages, tools=None, cache_breakpoints=None):
        self.calls += 1
        return LLMResponse(
            text=self._text, tool_calls=[],
            usage={"input_tokens": 100, "output_tokens": 50,
                   "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            raw={},
        )


# ----- happy path + resolution ----------------------------------------------


def test_happy_path(tmp_path):
    sha = "a" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {"items": [
        {"type": "Overpotential", "value": 236.0, "unit_label": "mV", "evidence": _ev(0)},
        {"type": "TafelSlope", "value": 47.0, "unit_label": "mV/decade", "evidence": _ev(1)},
    ]}
    valid, errors = extract(paper_sha=sha, provider=_StubProvider(json.dumps(response)), cache=cache)
    assert errors == []
    assert len(valid) == 2
    overp = next(v for v in valid if type(v).__name__ == "Overpotential")
    ev = overp.evidence
    # bbox/page/source_text/parser/paper all derived from the cited span
    assert (ev.bbox_x0, ev.bbox_y0, ev.bbox_x1, ev.bbox_y1) == BBOX_OVERP
    assert ev.page == 1
    assert ev.source_text == SPAN_OVERP  # verbatim, never stripped
    assert ev.parser_name == "mineru"
    assert ev.paper.sha256 == sha


def test_source_text_kept_verbatim(tmp_path):
    """No-strip policy: LaTeX artifacts in the cited span survive into source_text."""
    sha = "1" * 64
    latex = "mass activity is 3343.37 \\, A g^{-1}_{Ir}"
    page = [{"type": "text", "content": latex, "bbox": [10, 10, 200, 30]}]
    cache = _seed_cache(tmp_path, sha, parser_text=json.dumps([page]))
    response = {"items": [
        {"type": "MassActivity", "value": 3343.37, "unit_label": "A/g", "evidence": _ev(0)},
    ]}
    valid, errors = extract(paper_sha=sha, provider=_StubProvider(json.dumps(response)), cache=cache)
    assert len(valid) == 1
    assert valid[0].evidence.source_text == latex  # `\,`, `^{-1}`, `_{Ir}` intact


def test_resolve_spans_unions_multiple_ids():
    """Citing >1 span unions their bboxes; source_text concatenates; page from cited."""
    spans = [(3, "the overpotential was 236", (60.0, 100.0, 300.0, 120.0)),
             (3, "mV at 10 mA cm-2", (60.0, 122.0, 280.0, 142.0))]
    ev = _resolve_spans({"spans": [0, 1]}, spans, paper_sha="z" * 64, parser_name="dots")
    assert (ev["bbox_x0"], ev["bbox_y0"], ev["bbox_x1"], ev["bbox_y1"]) == (60.0, 100.0, 300.0, 142.0)
    assert ev["page"] == 3
    assert ev["source_text"] == "the overpotential was 236 mV at 10 mA cm-2"
    assert ev["parser_name"] == "dots"


# ----- error routing --------------------------------------------------------


def test_invalid_span_citation_routed_to_errors(tmp_path):
    """Empty or out-of-range span ids → errors (can't attach provenance)."""
    sha = "b" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {"items": [
        {"type": "Overpotential", "value": 236.0, "unit_label": "mV", "evidence": {"spans": []}},
        {"type": "Overpotential", "value": 236.0, "unit_label": "mV", "evidence": {"spans": [99]}},
    ]}
    valid, errors = extract(paper_sha=sha, provider=_StubProvider(json.dumps(response)), cache=cache)
    assert valid == []
    assert len(errors) == 2
    assert all(isinstance(e, ValueError) and "span citation" in str(e) for e, _ in errors)


def test_mis_citation_guard(tmp_path):
    """A value whose digits aren't in the cited span → likely mis-citation → error."""
    sha = "c" * 64
    cache = _seed_cache(tmp_path, sha)
    # value 999 cited to span 0, which states 236 → guard fires
    response = {"items": [
        {"type": "Overpotential", "value": 999.0, "unit_label": "mV", "evidence": _ev(0)},
    ]}
    valid, errors = extract(paper_sha=sha, provider=_StubProvider(json.dumps(response)), cache=cache)
    assert valid == []
    assert len(errors) == 1
    assert "mis-citation" in str(errors[0][0])


def test_validation_error_partial(tmp_path):
    """Bad item (extra field) → errors; the rest validate."""
    sha = "d" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {"items": [
        {"type": "Overpotential", "value": 236.0, "unit_label": "mV", "evidence": _ev(0)},
        {"type": "TafelSlope", "value": 47.0, "unit_label": "mV/decade", "evidence": _ev(1),
         "notes": "extra field, forbidden"},
    ]}
    valid, errors = extract(paper_sha=sha, provider=_StubProvider(json.dumps(response)), cache=cache)
    assert len(valid) == 1
    assert len(errors) == 1
    assert isinstance(errors[0][0], ValidationError)


def test_unknown_class(tmp_path):
    sha = "e" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {"items": [{"type": "BogusClass", "value": 0.0}]}
    valid, errors = extract(paper_sha=sha, provider=_StubProvider(json.dumps(response)), cache=cache)
    assert valid == []
    assert len(errors) == 1 and isinstance(errors[0][0], KeyError)


def test_baseclass_type_does_not_crash_batch(tmp_path):
    """`type: BaseModel` (a pydantic re-export) lands in errors, doesn't crash."""
    sha = "f" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {"items": [
        {"type": "BaseModel", "value": 0.0},
        {"type": "Overpotential", "value": 236.0, "unit_label": "mV", "evidence": _ev(0)},
    ]}
    valid, errors = extract(paper_sha=sha, provider=_StubProvider(json.dumps(response)), cache=cache)
    assert len(valid) == 1 and type(valid[0]).__name__ == "Overpotential"
    assert len(errors) == 1 and isinstance(errors[0][0], KeyError)


def test_missing_evidence_rejected(tmp_path):
    """A measurement with no evidence dict → errors."""
    sha = "2" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {"items": [
        {"type": "Overpotential", "value": 236.0, "unit_label": "mV"},  # no evidence
        {"type": "TafelSlope", "value": 47.0, "unit_label": "mV/decade", "evidence": _ev(1)},
    ]}
    valid, errors = extract(paper_sha=sha, provider=_StubProvider(json.dumps(response)), cache=cache)
    assert len(valid) == 1 and type(valid[0]).__name__ == "TafelSlope"
    assert len(errors) == 1


def test_wrong_unit_rejected(tmp_path):
    """C2: wrong unit ("V" for an mV slot) → errors; correct paper-faithful spelling passes."""
    sha = "3" * 64
    page = [
        {"type": "text", "content": "the overpotential was 236 mV", "bbox": [10, 10, 200, 30]},
        {"type": "text", "content": "TOF of 1.665 s^{-1}", "bbox": [10, 40, 200, 60]},
    ]
    cache = _seed_cache(tmp_path, sha, parser_text=json.dumps([page]))
    response = {"items": [
        {"type": "Overpotential", "value": 236.0, "unit_label": "V", "evidence": _ev(0)},
        {"type": "TurnoverFrequency", "value": 1.665, "unit_label": "s^{-1}", "evidence": _ev(1)},
    ]}
    valid, errors = extract(paper_sha=sha, provider=_StubProvider(json.dumps(response)), cache=cache)
    assert len(valid) == 1 and type(valid[0]).__name__ == "TurnoverFrequency"  # s^{-1} == 1/s
    assert len(errors) == 1 and "canonical" in str(errors[0][0])


def test_unparseable_response_routes_to_errors(tmp_path):
    """A page whose response isn't {"items":[...]} → page-level error, no crash."""
    sha = "4" * 64
    cache = _seed_cache(tmp_path, sha)
    valid, errors = extract(
        paper_sha=sha, provider=_StubProvider(json.dumps({"items": {"not": "a list"}})), cache=cache,
    )
    assert valid == []
    assert len(errors) == 1 and isinstance(errors[0][0], ValueError)


def test_unknown_skill_name_friendly_error(tmp_path):
    sha = "9" * 64
    cache = _seed_cache(tmp_path, sha)
    with pytest.raises(ValueError, match="unknown skill: 'nope'.*Available"):
        extract(paper_sha=sha, skill_name="nope", provider=_StubProvider("{}"), cache=cache)


def test_cache_miss_raises(tmp_path):
    sha = "5" * 64
    cache = ParserCache(db_path=str(tmp_path / "empty.db"), cache_dir=tmp_path / "cache")
    with pytest.raises(FileNotFoundError):
        extract(paper_sha=sha, provider=_StubProvider("{}"), cache=cache)


# ----- chandra (no geometry) + dedup + schema -------------------------------


def test_chandra_no_geometry_extracts_nothing(tmp_path):
    """Chandra is markdown → no spans → no pages → no LLM call, empty result."""
    sha = "7" * 64
    cache = _seed_cache(tmp_path, sha, parser_name="chandra",
                        parser_text="# Title\n\nThe overpotential was 236 mV.\n", suffix=".md")
    stub = _StubProvider(json.dumps({"items": []}))
    valid, errors = extract(paper_sha=sha, parser_name="chandra", provider=stub, cache=cache)
    assert valid == [] and errors == []
    assert stub.calls == 0  # no spans → never calls the LLM


def test_stringy_condition_coerced(tmp_path):
    """A unit-bearing string condition field is coerced to float, not fatal to the
    measurement (the LLM intermittently emits `current_density: "10 mA cm-2"`)."""
    sha = "8" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {"items": [
        {"type": "Overpotential", "value": 236.0, "unit_label": "mV",
         "condition": {"current_density": "10 mA cm-2"}, "evidence": _ev(0)},
    ]}
    valid, errors = extract(paper_sha=sha, provider=_StubProvider(json.dumps(response)), cache=cache)
    assert errors == [] and len(valid) == 1
    assert valid[0].condition.current_density == 10.0


def test_dedup_keeps_distinct_same_value():
    """Two catalysts reporting the same value (different source spans) are kept;
    only an identical-source duplicate collapses."""
    from schema.generated.pydantic import Evidence, Overpotential, Paper

    def _mk(src):
        ev = Evidence(paper=Paper(sha256="a" * 64), page=1, bbox_x0=0.0, bbox_y0=0.0,
                      bbox_x1=1.0, bbox_y1=1.0, parser_name="mineru", source_text=src)
        return Overpotential(value=236.0, unit_label="mV", evidence=ev)
    out = _dedup([_mk("catalyst A is 236 mV"), _mk("catalyst B is 236 mV"), _mk("catalyst A is 236 mV")])
    assert len(out) == 2  # A and B kept (distinct source_text); A's exact dup dropped


def test_dedup_drops_restated_measurements():
    """Same (type, value, unit) restated on multiple pages collapses to one."""
    from schema.generated.pydantic import Overpotential

    def _mk():
        return Overpotential(value=236.0, unit_label="mV")
    out = _dedup([_mk(), _mk(), Overpotential(value=298.0, unit_label="mV")])
    assert len(out) == 2
    assert sorted(v.value for v in out) == [236.0, 298.0]


def test_schema_for_prompt_strips_runtime_evidence_fields():
    """The LLM is shown Evidence WITHOUT the runtime-filled fields (it cites span ids)."""
    raw = Path("schema/generated/jsonschema.json").read_text()
    ev = json.loads(_schema_for_prompt(raw))["$defs"]["Evidence"]
    for k in ("paper", "page", "bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1", "source_text", "parser_name"):
        assert k not in ev["properties"]
    assert ev["required"] == []


# ----- per-parser projection + resolution -----------------------------------


@pytest.mark.parametrize(
    "parser,parser_text,expected_bbox",
    [
        ("dots",
         json.dumps({"pages": [[{"text": "overpotential 236 mV", "bbox": [60, 100, 500, 130]}]]}),
         (60.0, 100.0, 500.0, 130.0)),
        ("paddle",
         json.dumps({"pages": [{"res": {"page_index": 0, "parsing_res_list": [
             {"block_content": "overpotential 236 mV", "block_bbox": [60, 100, 500, 130]}]}}]}),
         (60.0, 100.0, 500.0, 130.0)),
        ("docling",
         json.dumps({"texts": [{"text": "overpotential 236 mV",
             "prov": [{"page_no": 1, "bbox": {"l": 60, "t": 200, "r": 500, "b": 180}}]}]}),
         (60.0, 200.0, 500.0, 180.0)),
    ],
)
def test_per_parser_projection_and_resolution(parser, parser_text, expected_bbox):
    """Each parser's native geometry → spans → id citation resolves to the right bbox."""
    spans = _load_spans(parser, parser_text)
    assert spans, f"{parser}: adapter produced no spans"
    ev = _resolve_spans({"spans": [0]}, spans, "x" * 64, parser)
    assert (ev["bbox_x0"], ev["bbox_y0"], ev["bbox_x1"], ev["bbox_y1"]) == expected_bbox


def test_docling_table_projected():
    """docling tables (separate `tables` array) are projected as citable spans."""
    data = {"texts": [], "tables": [{
        "prov": [{"page_no": 2, "bbox": {"l": 10, "t": 90, "r": 400, "b": 60}}],
        "data": {"table_cells": [{"text": "overpotential"}, {"text": "236 mV"}]},
    }]}
    spans = _load_spans("docling", json.dumps(data))
    assert len(spans) == 1
    page_no, text, bbox = spans[0]
    assert page_no == 2 and bbox == (10.0, 90.0, 400.0, 60.0)
    assert "236 mV" in text


def test_mineru_equation_captured():
    """mineru equation LaTeX (under content.math_content) is projected as a span."""
    page = [{"type": "equation_interline",
             "content": {"math_content": "\\mathrm{ECSA} = R_f S", "math_type": "latex"},
             "bbox": [100, 100, 300, 130]}]
    spans = _load_spans("mineru", json.dumps([page]))
    assert len(spans) == 1
    assert "ECSA" in spans[0][1]


def test_f3_classes_modeled():
    """T52 (closes T18a F3): SpecificActivity + Stability are Measurement classes
    with canonical units, so the extractor recognizes and validates them."""
    from palimpsest.tools.extract import _MEASUREMENT_NAMES
    from palimpsest.normalize import canonical_unit

    assert {"SpecificActivity", "Stability"} <= _MEASUREMENT_NAMES
    assert canonical_unit("SpecificActivity") == "mA/cm2"
    assert canonical_unit("Stability") == "h"


def test_deepseek_deterministic_config():
    """T52: extraction runs at temperature=0 with thinking disabled (lower variance)."""
    from palimpsest.providers import DeepSeekProvider

    assert DeepSeekProvider.extra_request["temperature"] == 0
    assert DeepSeekProvider.extra_request["thinking"] == {"type": "disabled"}


# ----- live test ------------------------------------------------------------


@pytest.mark.live
def test_live_extract(tmp_path):
    """Real DeepSeek (deepseek-v4-flash), per-page, on a paper sha cached by T16."""
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")
    matches = sorted(Path("cache").glob("*/mineru.json"))
    if not matches:
        pytest.skip("no cache/<sha>/mineru.json found; run T16 first")
    sha = matches[0].parent.name
    cache = ParserCache()
    meter = CostMeter(str(tmp_path / "live.db"))
    valid, errors = extract(paper_sha=sha, cost_meter=meter, cache=cache)
    print(f"\nlive extract: {len(valid)} valid, {len(errors)} errors, spend €{meter.total_eur():.4f}")
    for v in valid:
        print(" ", type(v).__name__, v.model_dump_json()[:90])
    assert len(valid) >= 5, f"got only {len(valid)} valid instances"
    assert 0 < meter.total_eur() < 1.0
