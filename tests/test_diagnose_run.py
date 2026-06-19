"""T70 — diagnose_run tests. Pure SQLite, no network, no GPU, €0.

`diagnose_run` is the read-only pattern summarizer over the same persisted drop
reasons `extraction_report` (T58) lists flatly: it *buckets* the drops by reason
and flags a bucket SYSTEMATIC when one error recurs (the V≠mV prompt/skill bug)
versus noise (a lone mis-citation), with a recommended action per bucket. The
in-loop nudge (`_drop_nudge`) is what turns a drop-heavy `extract_paper` result
into a prompt for the agent to call this tool and decide.
"""

from __future__ import annotations

import json
from pathlib import Path

from palimpsest.runs import ExtractionRunLog
from palimpsest.tools import TOOLS
from palimpsest.tools.diagnose_run import diagnose_run
from palimpsest.tools.run_paper import _drop_nudge

SHA_A = "a" * 64


def _log(tmp_path: Path) -> ExtractionRunLog:
    return ExtractionRunLog(db_path=str(tmp_path / "runs.db"))


def _record(log, sha=SHA_A, parser="mineru", *, n_extracted, n_inserted,
            n_errors, errors_json):
    log.record(
        paper_sha256=sha, run_id=f"run-{parser}", parser_name=parser,
        skill_name="oer-extraction", n_errors=n_errors, n_extracted=n_extracted,
        n_validated=n_inserted, n_inserted=n_inserted, errors_json=errors_json,
    )


# Reason strings are copied VERBATIM from tools/extract.py's str(exc) — the
# bucketer keys on substrings of these, so a fixture that paraphrases would let a
# wrong key pass (exactly how the original "no resolvable span" key shipped broken).
def _unit(i):
    return {"stage": "extract",
            "reason": "unit_label 'V' != canonical 'mV' for Overpotential",
            "item": f"{{'value': {i}}}"}


def _miscite():
    return {"stage": "extract",
            "reason": "likely mis-citation for Overpotential: value '511' "
                      "not found in cited span(s)",
            "item": "{'value': 511}"}


def _no_span(i):
    return {"stage": "extract",
            "reason": "no valid span citation for Overpotential; evidence=None",
            "item": f"{{'value': {i}}}"}


def _malformed():
    return {"stage": "extract",
            "reason": "item is str, expected dict",
            "item": "{'raw': 'oops'}"}


# The two markerless extract-stage drops (str(exc) verbatim, captured from
# pydantic / extract.py): an unknown-class KeyError and a Pydantic ValidationError.
# Neither carries a stable substring of its own → both fall to the catch-all bucket.
def _unknown_class():
    return {"stage": "extract", "reason": "'Bogus'", "item": "{'type': 'Bogus'}"}


def _validation():
    return {"stage": "extract",
            "reason": "1 validation error for Overpotential\nnotes\n  Extra inputs "
                      "are not permitted [type=extra_forbidden, input_value='x', "
                      "input_type=str]",
            "item": "{'notes': 'x'}"}


def test_card_case_unit_mismatch_is_systematic_miscitation_is_noise(tmp_path):
    """8/9 same unit-mismatch → SYSTEMATIC with a re-extract/skill recommendation;
    1/9 mis-citation → noise. The card's headline distinction."""
    log = _log(tmp_path)
    drops = [_unit(i) for i in range(8)] + [_miscite()]
    _record(log, n_extracted=0, n_inserted=0, n_errors=9,
            errors_json=json.dumps(drops))

    out = diagnose_run(SHA_A, "mineru", run_log=log)

    assert "unit mismatch" in out
    assert "8/9" in out
    assert "SYSTEMATIC" in out
    # the unit-mismatch line recommends re-extract after fixing the skill/units
    unit_line = next(ln for ln in out.splitlines() if "unit mismatch" in ln)
    assert "re-extract" in unit_line.lower()
    assert "skill" in unit_line.lower() or "unit" in unit_line.lower()
    # the lone mis-citation is noise, not flagged systematic
    miscite_line = next(ln for ln in out.splitlines() if "mis-citation" in ln)
    assert "noise" in miscite_line.lower()
    assert "SYSTEMATIC" not in miscite_line


def test_no_run_recorded_is_friendly(tmp_path):
    out = diagnose_run(SHA_A, "mineru", run_log=_log(tmp_path))
    assert "no extraction run" in out.lower()
    assert SHA_A[:8] in out
    assert "mineru" in out


def test_clean_run_reports_no_drops(tmp_path):
    log = _log(tmp_path)
    _record(log, n_extracted=12, n_inserted=12, n_errors=0,
            errors_json=json.dumps([]))
    out = diagnose_run(SHA_A, "mineru", run_log=log)
    assert "no drops" in out.lower()


def test_pre_t58_run_without_reasons_is_honest(tmp_path):
    """Counts show drops but errors_json is NULL (pre-T58 row): can't bucket
    what wasn't recorded — say so rather than reporting zero patterns."""
    log = _log(tmp_path)
    _record(log, n_extracted=10, n_inserted=8, n_errors=0, errors_json=None)
    out = diagnose_run(SHA_A, "mineru", run_log=log)
    assert "2 dropped" in out
    assert "not recorded" in out.lower()


def test_mixed_buckets_across_stages(tmp_path):
    """shacl + insert + extract drops each land in their own bucket; none of
    them reaches the systematic threshold (counts of 1) → all noise."""
    log = _log(tmp_path)
    drops = [
        _unit(0),
        {"stage": "shacl", "reason": "missing palimpsest:parserName",
         "type": "Overpotential"},
        {"stage": "insert", "reason": "refuse to insert without Evidence",
         "type": "TafelSlope"},
    ]
    _record(log, n_extracted=0, n_inserted=0, n_errors=3,
            errors_json=json.dumps(drops))
    out = diagnose_run(SHA_A, "mineru", run_log=log)
    assert "unit mismatch" in out
    assert "SHACL violation" in out
    assert "insert refusal" in out
    assert "SYSTEMATIC" not in out  # every bucket is a single drop → noise


def test_each_extract_reason_buckets_correctly(tmp_path):
    """Every distinct extract-stage reason string lands in its OWN bucket, not the
    generic fallback. This is the regression guard for the bucket substring keys:
    if a key drifts from extract.py's real str(exc), the matching kind silently
    collapses into 'schema/validation error' (the bug an earlier key shipped with).
    Each kind appears 3× so its bucket crosses the systematic threshold and the
    distinct labels are unambiguous."""
    log = _log(tmp_path)
    drops = (
        [_unit(i) for i in range(3)]
        + [_no_span(i) for i in range(3)]
        + [_malformed() for _ in range(3)]
    )
    _record(log, n_extracted=0, n_inserted=0, n_errors=9,
            errors_json=json.dumps(drops))
    out = diagnose_run(SHA_A, "mineru", run_log=log)

    assert "unit mismatch" in out
    assert "unresolvable evidence" in out      # NOT mis-bucketed (guards B1)
    assert "malformed item" in out
    # the unresolvable-evidence kind must NOT be labeled schema/validation error
    assert "schema/validation error" not in out


def test_markerless_extract_drops_bucket_as_schema_validation(tmp_path):
    """The catch-all bucket is reachable: unknown-class KeyError + Pydantic
    ValidationError drops carry no stable substring of their own, so they land in
    'schema/validation error' (positive coverage, not just absence) with the
    check_skill recommendation. Uses verbatim str(exc) strings."""
    log = _log(tmp_path)
    drops = [_unknown_class(), _validation(), _validation()]
    _record(log, n_extracted=0, n_inserted=0, n_errors=3,
            errors_json=json.dumps(drops))
    out = diagnose_run(SHA_A, "mineru", run_log=log)

    assert "schema/validation error" in out
    sv_line = next(ln for ln in out.splitlines() if "schema/validation error" in ln)
    assert "3/3" in sv_line                 # all three landed here, none elsewhere
    assert "check_skill" in sv_line
    # a markerless ValidationError must not be mistaken for a more specific bucket
    assert "unit mismatch" not in out
    assert "unresolvable evidence" not in out
    # Forward guard: diagnose_run renders only bucket labels + recommendations,
    # never a drop's raw `reason` — so a multi-line ValidationError reason can't
    # leak newlines (or its content) into the report. Holds structurally today;
    # this fails if a future _render starts echoing reason text without collapsing.
    assert "\n  Extra inputs" not in out
    assert "extra_forbidden" not in out


def test_pdf_path_resolves_to_sha(tmp_path, monkeypatch):
    log = _log(tmp_path)
    _record(log, n_extracted=0, n_inserted=0, n_errors=3,
            errors_json=json.dumps([_unit(0), _unit(1), _unit(2)]))
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(
        "palimpsest.tools.read_paper.read_paper",
        lambda path: {"sha256": SHA_A},
    )
    out = diagnose_run(str(pdf), "mineru", run_log=log)
    assert "SYSTEMATIC" in out  # 3 unit mismatches → systematic


def test_registered_with_required_paper():
    assert "diagnose_run" in TOOLS
    schema = TOOLS["diagnose_run"].tool_schema
    assert schema["name"] == "diagnose_run"
    assert schema["input_schema"]["required"] == ["paper"]


# --- the in-loop nudge (run_paper.py) ------------------------------------

def test_drop_nudge_fires_only_on_real_drops():
    nudge = _drop_nudge(4, "papers/x.pdf", "mineru")
    assert "diagnose_run" in nudge
    assert "papers/x.pdf" in nudge
    assert "mineru" in nudge
    assert "4" in nudge


def test_drop_nudge_silent_when_nothing_dropped():
    assert _drop_nudge(0, "papers/x.pdf", "mineru") == ""
