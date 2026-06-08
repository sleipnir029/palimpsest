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
from pathlib import Path

import pytest
from dotenv import load_dotenv
from pydantic import ValidationError

from palimpsest.cache import ParserCache
from palimpsest.cost import CostMeter
from palimpsest.providers.anthropic import LLMResponse
from palimpsest.tools.extract import extract

# Match the test_agent.py pattern: load .env so live tests find the API key.
load_dotenv()


# ----- helpers --------------------------------------------------------------


def _seed_cache(tmp_path: Path, sha: str, parser_text: str = '{"stub": true}') -> ParserCache:
    """Build a ParserCache with one paper + one mineru run pointing at a real file."""
    cache_dir = tmp_path / "cache"
    cache = ParserCache(db_path=str(tmp_path / "test.db"), cache_dir=cache_dir)
    cache.add_paper(sha256=sha, filename="x.pdf", page_count=12)
    rel = f"{sha}/mineru.json"
    out = cache_dir / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(parser_text)
    cache.insert_parser_run(
        sha256=sha,
        parser_name="mineru",
        parser_ver="test",
        output_path=rel,
        gpu_seconds=0.0,
        gpu_cost_eur=0.0,
        run_id="r1",
    )
    return cache


def _evidence(sha: str) -> dict:
    return {
        "paper": {"sha256": sha},
        "page": 3,
        "bbox_x0": 10.0,
        "bbox_y0": 20.0,
        "bbox_x1": 30.0,
        "bbox_y1": 40.0,
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
    """T19 audit + F4 split made Evidence.{paper,page,bbox_*,parser_name} required.

    Provenance is CLAUDE.md's non-negotiable; missing any required slot MUST
    surface as a ValidationError so the agent can re-prompt rather than ship
    an identity-less Evidence into the graph.
    """
    sha = "d" * 64
    cache = _seed_cache(tmp_path, sha)
    bad_evidence = {
        "paper": {"sha256": sha},
        "bbox_x0": 1.0, "bbox_y0": 2.0, "bbox_x1": 3.0, "bbox_y1": 4.0,
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
    assert isinstance(errors[0][0], ValidationError)


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
        "page": 3,
        "bbox_x0": 10.0, "bbox_y0": 20.0, "bbox_x1": 30.0, "bbox_y1": 40.0,
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


# ----- live test ------------------------------------------------------------


@pytest.mark.live
def test_live_extract(tmp_path):
    """Real Sonnet call on a paper sha already cached by T16 (~€0.30)."""
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
