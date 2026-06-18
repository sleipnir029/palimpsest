"""T58 — extraction_report tests. Pure SQLite, no network, no GPU, €0.

The tool reads the latest extraction run's persisted drop reasons (T58 errors_json
on extraction_runs, written by pipeline.run_paper) and renders them so the human
or agent can see *why* measurements are missing — the trust gap workspace_status
(T57) could only tease with a count.
"""

from __future__ import annotations

import json
from pathlib import Path

from palimpsest.runs import ExtractionRunLog
from palimpsest.tools import TOOLS
from palimpsest.tools.extraction_report import extraction_report

SHA_A = "a" * 64

_DROPS = [
    {"stage": "extract", "reason": "value 236 not in cited span", "item": "{'value': 236}"},
    {"stage": "extract", "reason": "unit V != mV", "item": "{'value': 1.7}"},
    {"stage": "shacl", "reason": "missing palimpsest:parserName", "type": "Overpotential"},
    {"stage": "insert", "reason": "refuse to insert without Evidence", "type": "TafelSlope"},
]


def _log(tmp_path: Path) -> ExtractionRunLog:
    return ExtractionRunLog(db_path=str(tmp_path / "runs.db"))


def _record(log, sha=SHA_A, parser="mineru", *, n_extracted, n_inserted,
            n_errors, errors_json):
    # run_id is the PK with sha (not parser), so distinct runs need distinct ids.
    log.record(
        paper_sha256=sha, run_id=f"run-{parser}", parser_name=parser,
        skill_name="oer-extraction", n_errors=n_errors, n_extracted=n_extracted,
        n_validated=n_inserted, n_inserted=n_inserted, errors_json=errors_json,
    )


def test_lists_each_dropped_item_with_reason(tmp_path):
    log = _log(tmp_path)
    # 2 extract errors + 3 Pydantic-valid, of which 1 SHACL-drop + 1 insert-refuse
    # → 1 inserted, 4 dropped.
    _record(log, n_extracted=3, n_inserted=1, n_errors=2,
            errors_json=json.dumps(_DROPS))

    out = extraction_report(SHA_A, "mineru", run_log=log)

    # workspace_status vocabulary: found / inserted / dropped.
    assert "5 found" in out      # n_extracted 3 + n_errors 2
    assert "1 inserted" in out
    assert "4 dropped" in out
    for d in _DROPS:
        assert d["reason"] in out
    # the stored item / type tail disambiguates same-reason drops
    assert "{'value': 236}" in out
    assert "Overpotential" in out


def test_no_run_recorded_is_friendly(tmp_path):
    out = extraction_report(SHA_A, "mineru", run_log=_log(tmp_path))
    assert "no extraction run" in out.lower()
    assert SHA_A[:8] in out  # names the paper it looked for
    assert "mineru" in out


def test_clean_run_reports_zero_dropped(tmp_path):
    log = _log(tmp_path)
    _record(log, n_extracted=12, n_inserted=12, n_errors=0,
            errors_json=json.dumps([]))
    out = extraction_report(SHA_A, "mineru", run_log=log)
    assert "12 inserted" in out
    assert "0 dropped" in out


def test_pre_t58_run_without_reasons(tmp_path):
    """A run recorded before T58 has counts showing drops but no errors_json —
    say so honestly rather than printing an empty reason list."""
    log = _log(tmp_path)
    _record(log, n_extracted=10, n_inserted=8, n_errors=0, errors_json=None)
    out = extraction_report(SHA_A, "mineru", run_log=log)
    assert "2 dropped" in out
    assert "not recorded" in out.lower()


def test_parser_argument_selects_the_run(tmp_path):
    log = _log(tmp_path)
    _record(log, parser="mineru", n_extracted=3, n_inserted=1, n_errors=2,
            errors_json=json.dumps(_DROPS))
    _record(log, parser="docling", n_extracted=6, n_inserted=6, n_errors=0,
            errors_json=json.dumps([]))
    assert "4 dropped" in extraction_report(SHA_A, "mineru", run_log=log)
    assert "0 dropped" in extraction_report(SHA_A, "docling", run_log=log)


def test_pdf_path_resolves_to_sha(tmp_path, monkeypatch):
    """A PDF path (not a 64-hex sha) is hashed via T07 read_paper."""
    log = _log(tmp_path)
    _record(log, n_extracted=3, n_inserted=1, n_errors=2,
            errors_json=json.dumps(_DROPS))

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(
        "palimpsest.tools.read_paper.read_paper",
        lambda path: {"sha256": SHA_A},
    )

    out = extraction_report(str(pdf), "mineru", run_log=log)
    assert "4 dropped" in out


def test_multiline_shacl_reason_renders_on_one_line(tmp_path):
    """A real pyshacl report is multi-line; the report must collapse it so a
    single drop doesn't become a wall of wrapped text."""
    log = _log(tmp_path)
    multiline = "Validation Report\nConforms: False\n  Constraint Violation:\n" \
                "    Focus node: <x>\n    minCount 1 on palimpsest:parserName"
    _record(log, n_extracted=1, n_inserted=0, n_errors=0,
            errors_json=json.dumps([
                {"stage": "shacl", "reason": multiline, "type": "Overpotential"},
            ]))
    out = extraction_report(SHA_A, "mineru", run_log=log)
    # The reason text survives but with no embedded newlines.
    assert "\n" not in out
    assert "minCount 1 on palimpsest:parserName" in out


def test_drop_without_item_or_type_renders_no_tail(tmp_path):
    """A bare drop (stage + reason only) renders `[stage] reason` with no tail."""
    log = _log(tmp_path)
    _record(log, n_extracted=1, n_inserted=0, n_errors=0,
            errors_json=json.dumps([{"stage": "shacl", "reason": "bad"}]))
    out = extraction_report(SHA_A, "mineru", run_log=log)
    assert out.endswith("[shacl] bad")  # no " (…)" tail appended


def test_registered_with_required_paper():
    assert "extraction_report" in TOOLS
    schema = TOOLS["extraction_report"].tool_schema
    assert schema["name"] == "extraction_report"
    assert schema["input_schema"]["required"] == ["paper"]
