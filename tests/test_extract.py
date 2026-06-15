"""T22 — extraction tool tests.

Offline tests use a stub provider returning canned JSON; the cache is per-test
(tmp_path) so the repo's `palimpsest.db`/`cache/` stay untouched. SkillLoader,
the generated JSON schema, and the normalization overlay are read from the real
repo files — pytest CWD is the repo root.

Live test (`--live` only) hits real Sonnet on a paper sha already cached by T16
and asserts ≥5 instances. Card target spend ≈ €0.30; we cap at €1 for safety.
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
    _load_spans,
    _resolve_bbox,
    _schema_without_bbox,
    extract,
)

# Match the test_agent.py pattern: load .env so live tests find the API key.
load_dotenv()


# ----- helpers --------------------------------------------------------------

# T49: the LLM now emits a verbatim `source_text` quote, and the runtime resolves
# the bbox by matching it against the parser's native geometry. So the seeded
# cache must carry real-shaped mineru geometry with a known span, and `_evidence`
# emits `source_text` + `page` (no bbox).
KNOWN_TEXT = "the overpotential was 236 mV at 10 mA cm-2"
KNOWN_PAGE = 3
KNOWN_BBOX = (63.0, 137.0, 929.0, 244.0)  # x0, y0, x1, y1


def _mineru_geometry() -> str:
    """A minimal real-shaped mineru output: list[page] of list[block].

    Pages 1..KNOWN_PAGE; the KNOWN_PAGE-th carries the matchable block plus a
    distractor that must NOT match the known snippet.
    """
    pages: list[list[dict]] = [[] for _ in range(KNOWN_PAGE)]
    pages[KNOWN_PAGE - 1] = [
        {"type": "text", "content": KNOWN_TEXT, "bbox": [63, 137, 929, 244]},
        {"type": "text", "content": "figure 2 shows the polarization trend",
         "bbox": [10, 300, 500, 360]},
        # A trivially short span ("h" is a substring of KNOWN_TEXT) sitting far
        # away: it must NOT be folded into the union bbox (the _MIN_SPAN_MATCH_CHARS
        # guard). Without the guard the recovered bbox would stretch to y=999.
        {"type": "text", "content": "h", "bbox": [1, 990, 5, 999]},
    ]
    return json.dumps(pages)


def _seed_cache(
    tmp_path: Path,
    sha: str,
    parser_name: str = "mineru",
    parser_text: str | None = None,
    suffix: str = ".json",
) -> ParserCache:
    """Build a ParserCache with one paper + one parser run pointing at a real file."""
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
        sha256=sha,
        parser_name=parser_name,
        parser_ver="test",
        output_path=rel,
        gpu_seconds=0.0,
        gpu_cost_eur=0.0,
        run_id="r1",
    )
    return cache


def _evidence(sha: str, source_text: str = KNOWN_TEXT, page: int = KNOWN_PAGE) -> dict:
    """Evidence in the T49 shape: a quote + page; bbox is runtime-resolved."""
    return {
        "paper": {"sha256": sha},
        "page": page,
        "source_text": source_text,
        "parser_name": "mineru",
    }


class _StubProvider:
    """Returns a fixed LLMResponse for any input; mirrors test_agent.py's pattern."""

    name = "stub"

    def __init__(self, response_text: str) -> None:
        self._text = response_text

    def complete(self, system, messages, tools=None, cache_breakpoints=None):
        return LLMResponse(
            text=self._text,
            tool_calls=[],
            usage={
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            raw={},
        )


# ----- offline tests --------------------------------------------------------


def test_happy_path(tmp_path):
    sha = "a" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {
        "items": [
            {
                "type": "Overpotential",
                "value": 236.0,
                "unit_label": "mV",
                "evidence": _evidence(sha),
            },
            {
                "type": "TafelSlope",
                "value": 47.0,
                "unit_label": "mV/decade",
                "evidence": _evidence(sha),
            },
        ]
    }
    valid, errors = extract(
        paper_sha=sha,
        provider=_StubProvider(json.dumps(response)),
        cache=cache,
    )
    assert len(valid) == 2
    assert errors == []
    assert type(valid[0]).__name__ == "Overpotential"
    assert valid[0].value == 236.0
    assert type(valid[1]).__name__ == "TafelSlope"
    assert valid[1].unit_label == "mV/decade"
    assert valid[0].evidence.parser_name == "mineru"


def test_validation_error_partial(tmp_path):
    """Bad item lands in `errors`; the rest validate. T22's re-prompt seam."""
    sha = "b" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {
        "items": [
            {
                "type": "Overpotential",
                "value": 236.0,
                "unit_label": "mV",
                "evidence": _evidence(sha),
            },
            # bad: extra "notes" field — ConfiguredBaseModel has extra="forbid".
            {
                "type": "TafelSlope",
                "value": 47.0,
                "unit_label": "mV/decade",
                "evidence": _evidence(sha),
                "notes": "should be rejected",
            },
            {
                "type": "ECSA",
                "value": 12.5,
                "unit_label": "cm2",
                "evidence": _evidence(sha),
            },
        ]
    }
    valid, errors = extract(
        paper_sha=sha,
        provider=_StubProvider(json.dumps(response)),
        cache=cache,
    )
    assert len(valid) == 2
    assert len(errors) == 1
    err, raw = errors[0]
    assert isinstance(err, ValidationError)
    assert raw["type"] == "TafelSlope"
    assert raw["notes"] == "should be rejected"


def test_unknown_class(tmp_path):
    """Unknown `type` discriminator lands in `errors` as a KeyError, not a crash."""
    sha = "c" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {"items": [{"type": "BogusClass", "value": 0.0}]}
    valid, errors = extract(
        paper_sha=sha,
        provider=_StubProvider(json.dumps(response)),
        cache=cache,
    )
    assert valid == []
    assert len(errors) == 1
    err, raw = errors[0]
    assert isinstance(err, KeyError)
    assert raw["type"] == "BogusClass"


def test_partial_evidence_fails(tmp_path):
    """Provenance is CLAUDE.md's non-negotiable; an item missing `page` MUST be
    routed to `errors`, not shipped into the graph.

    Under T49 the bbox is resolved by matching `source_text` on the stated
    `page`; with no `page` there is nothing to match against, so the item is
    rejected at the bbox gate (a ValueError) before instantiation. Either way it
    never reaches `valid`.
    """
    sha = "d" * 64
    cache = _seed_cache(tmp_path, sha)
    bad_evidence = {
        "paper": {"sha256": sha},
        "source_text": KNOWN_TEXT,
        "parser_name": "mineru",
        # `page` deliberately omitted
    }
    response = {
        "items": [
            {
                "type": "Overpotential",
                "value": 236.0,
                "unit_label": "mV",
                "evidence": bad_evidence,
            }
        ]
    }
    valid, errors = extract(
        paper_sha=sha,
        provider=_StubProvider(json.dumps(response)),
        cache=cache,
    )
    assert valid == []
    assert len(errors) == 1
    assert isinstance(errors[0][0], (ValueError, ValidationError))
    assert errors[0][1]["type"] == "Overpotential"


def test_provenance_sha_is_overwritten(tmp_path):
    """Caller-owned provenance overwrites whatever the LLM emitted.

    `paper.sha256` is a 64-char hash the LLM cannot know correctly — letting
    it emit one risks hallucinated hashes that silently corrupt the graph.
    `parser_name` is the caller's arg, not the LLM's guess. Both are injected
    after parsing, before Pydantic validation.
    """
    real_sha = "f" * 64
    cache = _seed_cache(tmp_path, real_sha)
    bad_evidence = {
        "paper": {"sha256": "WRONG_HALLUCINATED_SHA"},
        "page": KNOWN_PAGE,
        "source_text": KNOWN_TEXT,
        "parser_name": "GUESSED",
    }
    response = {
        "items": [
            {
                "type": "Overpotential",
                "value": 236.0,
                "unit_label": "mV",
                "evidence": bad_evidence,
            }
        ]
    }
    valid, errors = extract(
        paper_sha=real_sha,
        parser_name="mineru",
        provider=_StubProvider(json.dumps(response)),
        cache=cache,
    )
    assert errors == []
    assert len(valid) == 1
    assert valid[0].evidence.paper.sha256 == real_sha
    assert valid[0].evidence.parser_name == "mineru"


def test_baseclass_type_does_not_crash_batch(tmp_path):
    """LLM emitting `type: BaseModel` (pydantic re-export leaked into class map
    in v1) must NOT kill the batch. Item lands in errors; the rest survive.

    Without the `__module__ == _schema.__name__` filter in `_build_class_map`,
    `inspect.getmembers` surfaces `pydantic.BaseModel` and `RootModel`, and
    instantiating either via `cls(**item)` raises `PydanticUserError` (not
    `ValidationError`) — one bad item would crash the entire `extract()` call.
    """
    sha = "1" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {
        "items": [
            {"type": "BaseModel", "value": 0.0, "evidence": _evidence(sha)},
            {
                "type": "Overpotential",
                "value": 236.0,
                "unit_label": "mV",
                "evidence": _evidence(sha),
            },
        ]
    }
    valid, errors = extract(
        paper_sha=sha,
        provider=_StubProvider(json.dumps(response)),
        cache=cache,
    )
    assert len(valid) == 1
    assert type(valid[0]).__name__ == "Overpotential"
    assert len(errors) == 1
    err, raw = errors[0]
    assert isinstance(err, KeyError)
    assert raw["type"] == "BaseModel"


def test_missing_evidence_is_rejected(tmp_path):
    """Measurement subclass without an `evidence` dict at all lands in errors,
    not silently in `valid` with `evidence=None`.

    CLAUDE.md provenance non-negotiable says "if you cannot attach provenance,
    do not insert the triple and raise it loudly." Catching this at T22 lets
    the agent re-prompt before T24's expensive pyoxigraph insertion runs.
    """
    sha = "2" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {
        "items": [
            # no `evidence` key at all
            {"type": "Overpotential", "value": 236.0, "unit_label": "mV"},
            # well-formed control
            {
                "type": "TafelSlope",
                "value": 47.0,
                "unit_label": "mV/decade",
                "evidence": _evidence(sha),
            },
        ]
    }
    valid, errors = extract(
        paper_sha=sha,
        provider=_StubProvider(json.dumps(response)),
        cache=cache,
    )
    assert len(valid) == 1
    assert type(valid[0]).__name__ == "TafelSlope"
    assert len(errors) == 1
    err, raw = errors[0]
    assert isinstance(err, ValueError)
    assert "missing evidence" in str(err)
    assert raw["type"] == "Overpotential"


def test_items_not_a_list_raises(tmp_path):
    """`{"items": "foo"}` and similar shapes raise a clean ValueError,
    not an `AttributeError` from the iteration loop.
    """
    sha = "3" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {"items": {"not": "a list"}}
    with pytest.raises(ValueError, match="not parseable"):
        extract(
            paper_sha=sha,
            provider=_StubProvider(json.dumps(response)),
            cache=cache,
        )


def test_unknown_skill_name_friendly_error(tmp_path):
    """Unknown `skill_name` raises ValueError with the available list, NOT a
    bare KeyError.

    Agent's `_dispatch` (agent.py:102) catches any Exception and surfaces
    `f"error: {exc}"` as the tool_result content the LLM reads back. A bare
    `KeyError("nope")` stringifies as `'nope'` — opaque, no recovery path.
    The wrapped ValueError gives the LLM the actual available skill names
    so it can re-prompt with a correct one. The "Available: ..." substring
    is the LLM's only recovery signal — if a future maintainer reworks the
    message format, this test pins the consumer-facing shape.
    """
    sha = "9" * 64
    cache = _seed_cache(tmp_path, sha)
    with pytest.raises(ValueError, match="unknown skill: 'nope'.*Available"):
        extract(
            paper_sha=sha,
            skill_name="nope",
            provider=_StubProvider("{}"),
            cache=cache,
        )


def test_cache_miss_raises(tmp_path):
    """No cached parser output → loud FileNotFoundError, not a silent empty extract."""
    sha = "e" * 64
    cache = ParserCache(
        db_path=str(tmp_path / "empty.db"),
        cache_dir=tmp_path / "cache",
    )
    with pytest.raises(FileNotFoundError):
        extract(
            paper_sha=sha,
            provider=_StubProvider("{}"),
            cache=cache,
        )


# ----- T49: bbox resolution + unit validation -------------------------------


def test_parser_native_bbox_recovered(tmp_path):
    """The bbox is resolved from parser geometry by matching `source_text`,
    overwriting whatever the LLM emitted. This is the metric-meaningful case:
    T38 must score parser localization, not LLM transcription.
    """
    sha = "5" * 64
    cache = _seed_cache(tmp_path, sha)
    evidence = {
        "paper": {"sha256": sha},
        "page": KNOWN_PAGE,
        "source_text": KNOWN_TEXT,
        # a fabricated bbox the runtime MUST discard and replace
        "bbox_x0": 1.0, "bbox_y0": 1.0, "bbox_x1": 2.0, "bbox_y1": 2.0,
        "parser_name": "mineru",
    }
    response = {
        "items": [
            {"type": "Overpotential", "value": 236.0, "unit_label": "mV", "evidence": evidence}
        ]
    }
    valid, errors = extract(
        paper_sha=sha,
        provider=_StubProvider(json.dumps(response)),
        cache=cache,
    )
    assert errors == []
    assert len(valid) == 1
    ev = valid[0].evidence
    assert (ev.bbox_x0, ev.bbox_y0, ev.bbox_x1, ev.bbox_y1) == KNOWN_BBOX


def test_schema_shown_to_llm_omits_bbox():
    """Q1: the LLM is never shown bbox as its job. The Evidence definition in the
    schema embedded in the prompt has no bbox_* properties or required entries
    (the runtime resolves bbox from parser geometry), while other slots remain.
    """
    raw = Path("schema/generated/jsonschema.json").read_text()
    stripped = json.loads(_schema_without_bbox(raw))
    ev = stripped["$defs"]["Evidence"]
    for k in ("bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1"):
        assert k not in ev["properties"]
        assert k not in ev["required"]
    # untouched slots survive
    assert "source_text" in ev["properties"]
    assert "page" in ev["required"] and "parser_name" in ev["required"]


@pytest.mark.parametrize(
    "parser,parser_text,expected_bbox",
    [
        (
            "dots",
            json.dumps({"pages": [[
                {"text": "overpotential 236 mV at 10 mA cm-2", "bbox": [60, 100, 500, 130]},
            ]]}),
            (60.0, 100.0, 500.0, 130.0),
        ),
        (
            "paddle",
            json.dumps({"pages": [{"res": {"page_index": 0, "parsing_res_list": [
                {"block_content": "overpotential 236 mV at 10 mA cm-2", "block_bbox": [60, 100, 500, 130]},
            ]}}]}),
            (60.0, 100.0, 500.0, 130.0),
        ),
        (
            # docling bbox is a {l,t,r,b} dict in BOTTOMLEFT origin (t>b); the adapter
            # passes it through as (x0,y0,x1,y1) — coordinate convention is T38's job.
            "docling",
            json.dumps({"texts": [{
                "text": "overpotential 236 mV at 10 mA cm-2",
                "prov": [{"page_no": 1, "bbox": {"l": 60, "t": 200, "r": 500, "b": 180}}],
            }]}),
            (60.0, 200.0, 500.0, 180.0),
        ),
    ],
)
def test_per_parser_bbox_pipeline(parser, parser_text, expected_bbox):
    """Each parser's native geometry flows through `_load_spans` → `_resolve_bbox`
    and yields the span's own bbox.

    This is the end-to-end check for docling/dots/paddle that the live test (mineru
    only) didn't cover — and the ONLY feasible one for docling (4.86M tokens) and
    paddle (217K), whose raw output can't be fed to extraction whole.
    """
    span_text = "overpotential 236 mV at 10 mA cm-2"
    spans = _load_spans(parser, parser_text)
    assert spans, f"{parser}: adapter produced no spans"
    items = [{"type": "Overpotential", "evidence": {"page": 1, "source_text": span_text}}]
    _resolve_bbox(items, spans)
    ev = items[0]["evidence"]
    assert (ev["bbox_x0"], ev["bbox_y0"], ev["bbox_x1"], ev["bbox_y1"]) == expected_bbox


def test_resolve_bbox_prefers_containing_span_over_fragment():
    """A span that fully contains the quote wins over a far-away short fragment
    of the quote — the bbox stays TIGHT, not unioned/inflated.

    Whitespace-insensitive matching + unconditional union would otherwise fold a
    standalone ≥4-char fragment (e.g. a header 'overp...') into the union and
    blow the bbox up the page, defeating the precision T38 measures.
    """
    quote = "the overpotential was 236 mv at 10 ma cm-2"
    spans = [
        (3, quote, (60.0, 100.0, 500.0, 130.0)),     # contains the full quote
        (3, "overp", (5.0, 900.0, 40.0, 915.0)),       # 5-char fragment, far away
    ]
    items = [{"type": "Overpotential", "evidence": {"page": 3, "source_text": quote}}]
    _resolve_bbox(items, spans)
    ev = items[0]["evidence"]
    assert (ev["bbox_x0"], ev["bbox_y0"], ev["bbox_x1"], ev["bbox_y1"]) == (60.0, 100.0, 500.0, 130.0)


def test_resolve_bbox_unions_split_quote():
    """When NO single span contains the whole quote, the quote is split across
    spans — union those chunks (the card's intended union semantics).
    """
    spans = [
        (3, "the overpotential was 236 mV", (60.0, 100.0, 300.0, 120.0)),
        (3, "at 10 mA per square cm", (60.0, 122.0, 280.0, 142.0)),
        (3, "unrelated caption text here", (10.0, 800.0, 200.0, 820.0)),
    ]
    quote = "the overpotential was 236 mV at 10 mA per square cm"
    items = [{"type": "Overpotential", "evidence": {"page": 3, "source_text": quote}}]
    _resolve_bbox(items, spans)
    ev = items[0]["evidence"]
    # union of the two matching line spans; the far caption is not part of the quote
    assert (ev["bbox_x0"], ev["bbox_y0"], ev["bbox_x1"], ev["bbox_y1"]) == (60.0, 100.0, 300.0, 142.0)


def test_wrong_unit_rejected(tmp_path):
    """C2: a `unit_label` that is the WRONG unit is routed to `errors`, but a
    correct unit in paper-faithful spelling PASSES (normalize.units_match).

    "V" for an mV slot is a genuine 1000x error → rejected. "s⁻¹" for a 1/s slot
    is the same unit, differently spelled → accepted (the live-run case that the
    old exact-string match wrongly rejected).
    """
    sha = "6" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {
        "items": [
            # wrong unit: "V" instead of canonical "mV" — a real magnitude error
            {"type": "Overpotential", "value": 0.236, "unit_label": "V", "evidence": _evidence(sha)},
            # correct unit, canonical spelling
            {"type": "Overpotential", "value": 236.0, "unit_label": "mV", "evidence": _evidence(sha)},
            # correct unit, paper-faithful spelling — must still pass
            {"type": "TurnoverFrequency", "value": 1.665, "unit_label": "s⁻¹", "evidence": _evidence(sha)},
        ]
    }
    valid, errors = extract(
        paper_sha=sha,
        provider=_StubProvider(json.dumps(response)),
        cache=cache,
    )
    assert len(valid) == 2
    assert {type(v).__name__ for v in valid} == {"Overpotential", "TurnoverFrequency"}
    assert len(errors) == 1
    err, raw = errors[0]
    assert isinstance(err, ValueError)
    assert "canonical" in str(err)
    assert raw["unit_label"] == "V"


def test_chandra_no_geometry_routes_to_errors(tmp_path):
    """Chandra emits markdown with no geometry. Per the B-scope decision, its
    measurements cannot get a parser-native bbox and route to `errors` — the
    batch must NOT crash (the card's Chandra acceptance test, B variant).
    """
    sha = "7" * 64
    cache = _seed_cache(
        tmp_path, sha,
        parser_name="chandra",
        parser_text="# Title\n\nThe overpotential was 236 mV at 10 mA cm-2.\n",
        suffix=".md",
    )
    response = {
        "items": [
            {"type": "Overpotential", "value": 236.0, "unit_label": "mV", "evidence": _evidence(sha)}
        ]
    }
    valid, errors = extract(
        paper_sha=sha,
        parser_name="chandra",
        provider=_StubProvider(json.dumps(response)),
        cache=cache,
    )
    assert valid == []
    assert len(errors) == 1
    err, raw = errors[0]
    assert isinstance(err, ValueError)
    assert "no parser-native bbox" in str(err)
    assert raw["type"] == "Overpotential"


def test_no_match_snippet_routes_to_errors(tmp_path):
    """A `source_text` that quotes nothing in the parser geometry yields no bbox
    and routes to `errors`, rather than carrying a fabricated bbox forward.
    """
    sha = "8" * 64
    cache = _seed_cache(tmp_path, sha)
    response = {
        "items": [
            {
                "type": "Overpotential",
                "value": 236.0,
                "unit_label": "mV",
                "evidence": _evidence(sha, source_text="this phrase appears in no parser span"),
            }
        ]
    }
    valid, errors = extract(
        paper_sha=sha,
        provider=_StubProvider(json.dumps(response)),
        cache=cache,
    )
    assert valid == []
    assert len(errors) == 1
    assert isinstance(errors[0][0], ValueError)
    assert "no parser-native bbox" in str(errors[0][0])


# ----- live test ------------------------------------------------------------


@pytest.mark.live
def test_live_extract(tmp_path):
    """Real DeepSeek (deepseek-v4-flash) call on a paper sha cached by T16 (~€0.02).

    T50: the default provider is now DeepSeek, so this exercises the real
    extraction path on DeepSeek's Anthropic-compatible endpoint.
    """
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")
    matches = sorted(Path("cache").glob("*/mineru.json"))
    if not matches:
        pytest.skip("no cache/<sha>/mineru.json found; run T16 first")
    sha = matches[0].parent.name
    cache = ParserCache()  # repo defaults
    meter = CostMeter(str(tmp_path / "live.db"))
    valid, errors = extract(paper_sha=sha, cost_meter=meter, cache=cache)
    print(f"\nlive extract: {len(valid)} valid, {len(errors)} errors, spend €{meter.total_eur():.4f}")
    for v in valid:
        print(" ", type(v).__name__, v.model_dump_json()[:80])
    for exc, raw in errors:
        print(" ERR", type(exc).__name__, raw.get("type"))
    assert len(valid) >= 5, f"got only {len(valid)} valid instances"
    types_seen = {type(v).__name__ for v in valid}
    assert types_seen & {"Overpotential", "TafelSlope"}, (
        f"expected Overpotential or TafelSlope, got {types_seen}"
    )
    assert 0 < meter.total_eur() < 1.0, f"spend €{meter.total_eur():.4f} outside [0, 1]"
