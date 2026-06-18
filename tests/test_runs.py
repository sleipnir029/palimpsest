"""T57 — ExtractionRunLog tests. Pure SQLite, no network, no GPU.

The run log is the persisted observability gap T57 fills: run_paper computes
n_extracted/n_validated/n_inserted (and extract() computes the dropped `errors`
count) then currently throws them away. This records one row per extraction run
so workspace_status (T57) can report a REAL dropped count and T58 can later add
the per-item reasons — instead of re-running the LLM or fabricating a proxy.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from palimpsest.runs import ExtractionRunLog

SHA_A = "a" * 64
SHA_B = "b" * 64


def _mk(tmp_path: Path) -> ExtractionRunLog:
    return ExtractionRunLog(db_path=str(tmp_path / "runs.db"))


def _record(log: ExtractionRunLog, sha: str, run_id: str, **overrides) -> None:
    kw = dict(
        paper_sha256=sha,
        run_id=run_id,
        parser_name="mineru",
        skill_name="oer-extraction",
        n_errors=0,
        n_extracted=10,
        n_validated=10,
        n_inserted=10,
    )
    kw.update(overrides)
    log.record(**kw)


def test_latest_per_paper_empty(tmp_path):
    log = _mk(tmp_path)
    assert log.latest_per_paper() == {}


def test_record_and_read_back_counts(tmp_path):
    log = _mk(tmp_path)
    _record(log, SHA_A, "run-1", n_errors=2, n_extracted=12, n_validated=11, n_inserted=10)
    latest = log.latest_per_paper()
    assert set(latest) == {SHA_A}
    row = latest[SHA_A]
    assert (row["n_errors"], row["n_extracted"], row["n_validated"], row["n_inserted"]) == (2, 12, 11, 10)
    assert row["parser_name"] == "mineru"
    assert row["skill_name"] == "oer-extraction"


def test_latest_per_paper_takes_most_recent_run(tmp_path):
    log = _mk(tmp_path)
    _record(log, SHA_A, "run-old", n_extracted=5, n_inserted=5)
    _record(log, SHA_A, "run-new", n_extracted=14, n_inserted=14)
    latest = log.latest_per_paper()
    assert len(latest) == 1
    # The newer run (later rowid) wins, not the higher/lower count.
    assert latest[SHA_A]["n_extracted"] == 14
    assert latest[SHA_A]["run_id"] == "run-new"


def test_latest_per_paper_groups_by_paper(tmp_path):
    log = _mk(tmp_path)
    _record(log, SHA_A, "run-a")
    _record(log, SHA_B, "run-b", n_extracted=3, n_inserted=3)
    latest = log.latest_per_paper()
    assert set(latest) == {SHA_A, SHA_B}
    assert latest[SHA_B]["n_extracted"] == 3


def test_record_persists_across_reopen(tmp_path):
    db = str(tmp_path / "runs.db")
    log1 = ExtractionRunLog(db_path=db)
    _record(log1, SHA_A, "run-1", n_extracted=7, n_inserted=6)
    del log1
    log2 = ExtractionRunLog(db_path=db)
    assert log2.latest_per_paper()[SHA_A]["n_inserted"] == 6


# --- T58: per-item drop reasons (errors_json) --------------------------------

_REASONS = '[{"stage": "extract", "reason": "value 236 not in cited span"}, ' \
           '{"stage": "extract", "reason": "unit V != mV"}]'


def test_errors_json_defaults_to_none(tmp_path):
    """Existing callers that don't pass errors_json get NULL, not a crash."""
    log = _mk(tmp_path)
    _record(log, SHA_A, "run-1")
    assert log.latest_per_paper()[SHA_A]["errors_json"] is None


def test_errors_json_round_trips(tmp_path):
    log = _mk(tmp_path)
    _record(log, SHA_A, "run-1", errors_json=_REASONS)
    assert log.latest_per_paper()[SHA_A]["errors_json"] == _REASONS


def test_latest_run_returns_row_for_paper_and_parser(tmp_path):
    log = _mk(tmp_path)
    _record(log, SHA_A, "run-1", parser_name="mineru", n_extracted=12,
            n_inserted=10, errors_json=_REASONS)
    row = log.latest_run(SHA_A, "mineru")
    assert row is not None
    assert row["run_id"] == "run-1"
    assert row["n_extracted"] == 12
    assert row["errors_json"] == _REASONS


def test_latest_run_unknown_returns_none(tmp_path):
    log = _mk(tmp_path)
    _record(log, SHA_A, "run-1", parser_name="mineru")
    assert log.latest_run(SHA_B, "mineru") is None       # unknown paper
    assert log.latest_run(SHA_A, "docling") is None       # paper present, other parser


def test_latest_run_filters_by_parser(tmp_path):
    """A run with a different parser must not shadow the requested one."""
    log = _mk(tmp_path)
    _record(log, SHA_A, "run-mineru", parser_name="mineru", n_extracted=12)
    _record(log, SHA_A, "run-docling", parser_name="docling", n_extracted=6)
    assert log.latest_run(SHA_A, "mineru")["n_extracted"] == 12
    assert log.latest_run(SHA_A, "docling")["n_extracted"] == 6


def test_latest_run_takes_most_recent(tmp_path):
    log = _mk(tmp_path)
    _record(log, SHA_A, "run-old", parser_name="mineru", n_extracted=5)
    _record(log, SHA_A, "run-new", parser_name="mineru", n_extracted=14)
    assert log.latest_run(SHA_A, "mineru")["run_id"] == "run-new"


def test_migration_adds_errors_json_to_pre_t58_table(tmp_path):
    """A T57 DB (extraction_runs without errors_json) gains the column on open,
    without losing existing rows."""
    db = str(tmp_path / "runs.db")
    # Hand-build the pre-T58 table shape (no errors_json) and seed a row.
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE extraction_runs ("
        " paper_sha256 TEXT NOT NULL, run_id TEXT NOT NULL, extracted_at TEXT NOT NULL,"
        " parser_name TEXT NOT NULL, skill_name TEXT NOT NULL,"
        " n_errors INTEGER NOT NULL, n_extracted INTEGER NOT NULL,"
        " n_validated INTEGER NOT NULL, n_inserted INTEGER NOT NULL,"
        " PRIMARY KEY (paper_sha256, run_id));"
    )
    conn.execute(
        "INSERT INTO extraction_runs VALUES (?,?,?,?,?,?,?,?,?)",
        (SHA_A, "run-old", "2026-06-18T00:00:00+00:00", "mineru",
         "oer-extraction", 0, 8, 8, 8),
    )
    conn.commit()
    conn.close()

    log = ExtractionRunLog(db_path=db)  # must migrate, not raise
    # Old row survives and reads back with errors_json = NULL.
    old = log.latest_run(SHA_A, "mineru")
    assert old["n_extracted"] == 8
    assert old["errors_json"] is None
    # New writes can use the column.
    _record(log, SHA_B, "run-new", parser_name="mineru", errors_json=_REASONS)
    assert log.latest_run(SHA_B, "mineru")["errors_json"] == _REASONS
