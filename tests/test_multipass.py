"""T74 — unit tests for the multi-pass / ensemble extraction helpers.

`experiments/multipass.py`'s live wrappers (extract_union/extract_requery/
judge_filter) are integration code — verified by the live T74 run. But four pure
helpers decide what each arm actually keeps/misses, so they get focused offline
tests:
  - `dedup_by_value`     — cross-parser/cross-arm union must collapse the SAME
                           physical measurement (same type+value, different cite).
  - `missing_measurement_types` — the re-query arm's pass-2 target set.
  - `judge_keep`         — parse the judge's verdict; fail OPEN (keep all) so a
                           malformed judge reply never silently destroys recall.
  - `reachable_recall`   — recall normalized by the parser coverage ceiling.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))

import multipass  # noqa: E402
from palimpsest.providers import LLMResponse  # noqa: E402


class _JudgeStub:
    """Returns a fixed reply for the one judge call; records what it was asked."""

    name = "judge-stub"
    prices = {"input_tokens": 0.0, "output_tokens": 0.0}

    def __init__(self, text):
        self._text = text
        self.in_tokens = self.out_tokens = 0

    def complete(self, system, messages, tools=None):
        return LLMResponse(text=self._text, tool_calls=[], usage={}, raw={})


def _item(type_, value, source_text="s"):
    return {"type": type_, "value": value,
            "evidence": {"source_text": source_text}}


# --- dedup_by_value ---------------------------------------------------------

def test_dedup_by_value_collapses_same_type_value_across_cites():
    # docling and paddle both surface 236 mV → one measurement, not two.
    items = [_item("Overpotential", 236.0, "docling span"),
             _item("Overpotential", 236.0, "paddle span")]
    out = multipass.dedup_by_value(items)
    assert len(out) == 1
    assert out[0]["evidence"]["source_text"] == "docling span"  # first wins


def test_dedup_by_value_keeps_distinct_values():
    items = [_item("Overpotential", 236.0), _item("Overpotential", 298.0)]
    assert len(multipass.dedup_by_value(items)) == 2


def test_dedup_by_value_keeps_same_value_distinct_types():
    items = [_item("Overpotential", 40.0), _item("Stability", 40.0)]
    assert len(multipass.dedup_by_value(items)) == 2


# --- missing_measurement_types ----------------------------------------------

def test_missing_measurement_types_returns_sorted_absent():
    found = [_item("Overpotential", 236.0)]
    allt = {"Overpotential", "TafelSlope", "Stability"}
    assert multipass.missing_measurement_types(found, allt) == ["Stability", "TafelSlope"]


def test_missing_measurement_types_empty_when_all_present():
    found = [_item("Overpotential", 1.0), _item("TafelSlope", 2.0)]
    assert multipass.missing_measurement_types(found, {"Overpotential", "TafelSlope"}) == []


# --- judge_keep -------------------------------------------------------------

def test_judge_keep_parses_supported_flags():
    text = '{"supported": [true, false, true]}'
    assert multipass.judge_keep(text, 3) == {0, 2}


def test_judge_keep_fails_open_on_unparseable():
    # A malformed judge reply must NOT drop everything — keep all (precision pass
    # is best-effort; recall is the expensive thing we just bought).
    assert multipass.judge_keep("garbage", 3) == {0, 1, 2}


def test_judge_keep_fails_open_on_length_mismatch():
    # Wrong-length verdict array is untrustworthy → keep all.
    assert multipass.judge_keep('{"supported": [true]}', 3) == {0, 1, 2}


# --- judge_filter (DROP-only + fail-open integration) -----------------------

def test_judge_filter_drops_unsupported_and_returns_subset():
    items = [_item("Overpotential", 236.0, "236 mV"),
             _item("TafelSlope", 47.0, "figure caption, no slope text")]
    kept, raw = multipass.judge_filter(items, _JudgeStub('{"supported": [true, false]}'))
    assert [it["value"] for it in kept] == [236.0]   # subset, second dropped
    assert raw == '{"supported": [true, false]}'


def test_judge_filter_fails_open_on_garbage():
    # A malformed verdict must NOT delete real extractions (recall is what we paid for).
    items = [_item("Overpotential", 236.0), _item("TafelSlope", 47.0)]
    kept, _ = multipass.judge_filter(items, _JudgeStub("not json"))
    assert len(kept) == 2


def test_judge_filter_handles_none_evidence():
    # Provenance dict can be None on a malformed item — must not crash building the prompt.
    items = [{"type": "Overpotential", "value": 236.0, "evidence": None}]
    kept, _ = multipass.judge_filter(items, _JudgeStub('{"supported": [true]}'))
    assert len(kept) == 1


def test_judge_filter_empty_items_no_call():
    kept, raw = multipass.judge_filter([], _JudgeStub('{"supported": []}'))
    assert kept == [] and raw == ""


# --- reachable_recall -------------------------------------------------------

def test_reachable_recall_normalizes_by_ceiling():
    # 8 hits, 10 gold, 2 unreachable (coverage_gap) → 8/8 reachable = 1.0
    assert multipass.reachable_recall(hit=8, gt_total=10, coverage_gap=2) == 1.0


def test_reachable_recall_equals_recall_when_full_coverage():
    assert multipass.reachable_recall(hit=5, gt_total=10, coverage_gap=0) == 0.5


def test_reachable_recall_zero_when_nothing_reachable():
    assert multipass.reachable_recall(hit=0, gt_total=4, coverage_gap=4) == 0.0
