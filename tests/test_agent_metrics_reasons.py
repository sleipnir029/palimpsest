"""experiments/agent_metrics.py: refusal-reason buckets (thesis review, 2026-10-13).

The unit-aware citation check refuses with "span unit mismatch". It gets its own
bucket rather than folding into the unit-signature gate's "unit_mismatch".
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))

import agent_metrics  # noqa: E402


def test_span_unit_mismatch_bucket():
    reason = ("span unit mismatch for DegradationRate: value 460.0 is printed as "
              "'460 V' in the cited span, not in 'mV/h'")
    assert agent_metrics._classify_reason(reason) == "span_unit_mismatch"


def test_unit_signature_bucket_unchanged():
    assert agent_metrics._classify_reason(
        "unit_label 'V' != canonical 'mV' for Overpotential") == "unit_mismatch"
