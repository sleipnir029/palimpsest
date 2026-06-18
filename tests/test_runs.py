"""T57 — ExtractionRunLog tests. Pure SQLite, no network, no GPU.

The run log is the persisted observability gap T57 fills: run_paper computes
n_extracted/n_validated/n_inserted (and extract() computes the dropped `errors`
count) then currently throws them away. This records one row per extraction run
so workspace_status (T57) can report a REAL dropped count and T58 can later add
the per-item reasons — instead of re-running the LLM or fabricating a proxy.
"""

from __future__ import annotations

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
