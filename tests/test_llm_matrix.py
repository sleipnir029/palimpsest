"""T72 — unit tests for the matrix driver's load-bearing internals.

`experiments/llm_matrix.py` is an experiment driver (its end-to-end verification is
the live run + the CSV), but two internals decide the headline cost axis and the
reproducibility column, so they get focused offline tests:
  - `_UsageRecorder` sums token usage across the >1 complete() calls extract() makes
    when it batches by page → drives €/paper.
  - `_temperature` reads the configured temperature wherever it actually lives
    (an attribute for OpenAI-compat, `extra_request` for DeepSeek) so the CSV column
    isn't silently blank for the models that fix it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))

import llm_matrix  # noqa: E402
from palimpsest.providers import (  # noqa: E402
    AnthropicProvider,
    DeepSeekProvider,
    LLMResponse,
    OpenAICompatProvider,
)


class _FakeProvider:
    name = "fake"
    prices = {"input_tokens": 1.0}

    def __init__(self, usage=None):
        self.calls = 0
        self.last_kwargs = None
        self._usage = usage or {"input_tokens": 10, "output_tokens": 3}

    def complete(self, *a, **k):
        self.calls += 1
        self.last_kwargs = k
        return LLMResponse(text="{}", tool_calls=[], usage=self._usage, raw={})


def test_usage_recorder_accumulates_across_calls():
    rec = llm_matrix._UsageRecorder(_FakeProvider())
    rec.complete("s", [])
    rec.complete("s", [])
    assert rec.in_tokens == 20
    assert rec.out_tokens == 6


def test_usage_recorder_counts_all_input_tiers():
    # DeepSeek/Gemini auto-cache → most input lands under cache_read_*. The cost axis
    # must count every input tier, or it undercounts ~50x (the T72 first-run bug).
    inner = _FakeProvider(usage={
        "input_tokens": 28, "cache_read_input_tokens": 24548,
        "cache_creation_input_tokens": 100, "output_tokens": 2000,
    })
    rec = llm_matrix._UsageRecorder(inner)
    rec.complete("s", [])
    assert rec.in_tokens == 28 + 24548 + 100
    assert rec.out_tokens == 2000


def test_usage_recorder_disables_caching():
    # Clean per-paper cost: the recorder forces cache_breakpoints=None on every call.
    inner = _FakeProvider()
    rec = llm_matrix._UsageRecorder(inner)
    rec.complete("s", [], cache_breakpoints=["system"])
    assert inner.last_kwargs.get("cache_breakpoints") is None


def test_usage_recorder_forwards_name_and_prices():
    rec = llm_matrix._UsageRecorder(_FakeProvider())
    assert rec.name == "fake"
    assert rec.prices == {"input_tokens": 1.0}


def test_usage_recorder_picks_up_prices_set_after_construction():
    # The matrix sets inner.prices AFTER the factory builds the provider, then wraps.
    inner = OpenAICompatProvider(model="m", base_url="https://x/v1", api_key="k")
    inner.prices = {"input_tokens": 0.5, "output_tokens": 1.0}
    rec = llm_matrix._UsageRecorder(inner)
    assert rec.prices == {"input_tokens": 0.5, "output_tokens": 1.0}


def test_temperature_reads_attribute_for_openai_compat():
    p = OpenAICompatProvider(model="m", base_url="https://x/v1", api_key="k", temperature=0.0)
    assert llm_matrix._temperature(p) == 0.0


def test_temperature_reads_extra_request_for_deepseek():
    # DeepSeek fixes temperature=0 in extra_request, not as an attribute.
    assert llm_matrix._temperature(DeepSeekProvider(api_key="x")) == 0


def test_temperature_blank_when_unset():
    class _Bare:
        pass

    assert llm_matrix._temperature(_Bare()) == ""


def test_temperature_blank_for_anthropic():
    # Anthropic sets no temperature (API default) — column stays honestly blank, not 0.
    # Locks against a regression if someone adds a default temperature to extra_request.
    assert llm_matrix._temperature(AnthropicProvider(api_key="x", model="m")) == ""


# --- Part C: strict response_format schema (locks the OpenAI-strict invariants so a
# future schema regen — e.g. a new Condition enum without a null branch — fails HERE,
# offline, instead of silently erroring out every strict live call). ----------------

def _walk(node, fn):
    if isinstance(node, dict):
        fn(node)
        for v in node.values():
            _walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            _walk(v, fn)


def test_strict_response_format_is_openai_strict_compliant():
    import jsonschema

    rf = llm_matrix._strict_response_format()
    assert rf["type"] == "json_schema"
    js = rf["json_schema"]
    assert js["strict"] is True
    schema = js["schema"]
    jsonschema.Draft202012Validator.check_schema(schema)  # valid JSON Schema

    # OpenAI strict: every object is closed AND lists every property in `required`.
    def _closed(node):
        if node.get("type") == "object" and "properties" in node:
            assert node.get("additionalProperties") is False, node
            assert set(node.get("required", [])) == set(node["properties"]), node

    _walk(schema, _closed)

    # No dangling $ref (every ref resolves to a $def).
    defs = set(schema["$defs"])
    refs: set[str] = set()
    _walk(schema, lambda n: refs.add(n["$ref"].split("/")[-1]) if "$ref" in n else None)
    assert refs <= defs, f"dangling $ref(s): {refs - defs}"


def test_strict_schema_type_enum_covers_all_measurements():
    rf = llm_matrix._strict_response_format()
    item = rf["json_schema"]["schema"]["properties"]["items"]["items"]
    assert set(item["properties"]["type"]["enum"]) == set(llm_matrix._MEASUREMENT_NAMES)
    # evidence is span-ids only (NOT the bbox-laden generated Evidence def).
    assert item["properties"]["evidence"]["$ref"].endswith("EvidenceSpans")


def test_ground_truth_filters_to_cached_papers_with_gold():
    # _ground_truth scores a paper only if BOTH its <parser>.json cache AND a GOLD
    # entry exist — so the same gold drives Stage 2 (other parsers) with no change.
    from ab_extract import GOLD

    gt = llm_matrix._ground_truth("mineru")
    assert gt, "expected mineru gold papers (corpus fixtures present)"
    assert set(gt) <= set(GOLD)  # never score a paper without gold
    for sha, tuples in gt.items():
        assert tuples is GOLD[sha]  # values are the GOLD tuples, unchanged


def test_ground_truth_empty_for_unparsed_parser():
    assert llm_matrix._ground_truth("no_such_parser") == {}


def test_score_handles_null_value_pred():
    # `value` is schema-nullable, so a model can emit a measurement with value=None.
    # Regression: the dots Stage-2 run crashed on `abs(None - float)` in _matches.
    # A null-value extraction must NOT crash _score, can't match a numeric gold, but
    # still counts toward n_valid (it's a spurious output → lowers precision).
    from ab_extract import _score

    class Overpotential:  # class name = the Measurement type the scorer reads
        value = None

    tp, n_preds, recall, precision = _score([Overpotential()], [("Overpotential", 236.0)])
    assert tp == 0 and n_preds == 1 and recall == 0.0 and precision == 0.0
