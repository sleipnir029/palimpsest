"""ExtractionRunLog (T57): persist per-run extraction counts in palimpsest.db.

`run_paper` computes how many measurements were extracted, validated, and
inserted, and `extract()` computes how many the LLM produced but were rejected
pre-validation (the dropped `errors`). None of it was persisted — so a later,
read-only "what have I done?" query (T57 ``workspace_status``) had no way to
report a real dropped count without re-running the LLM. This records one row per
run, mirroring ``parser_runs`` (same DB, same SQLite-ledger architecture), so:

  * T57 surfaces the count teaser  (dropped = n_errors + n_extracted - n_inserted)
  * T58 reads the same table for the per-item reasons (it adds the error detail)

No FK to ``papers`` (cost_ledger sets the precedent): a run is an event, recorded
even if the paper row races or is pruned. ``latest_per_paper`` returns the most
recent run per paper (by insertion order / rowid), which is what an orientation
view wants — the current state, not the full history.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .cost import canonical_db  # one repo-root palimpsest.db, cwd-independent

_DDL = """
CREATE TABLE IF NOT EXISTS extraction_runs (
    paper_sha256 TEXT NOT NULL,
    run_id       TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    parser_name  TEXT NOT NULL,
    skill_name   TEXT NOT NULL,
    n_errors     INTEGER NOT NULL,
    n_extracted  INTEGER NOT NULL,
    n_validated  INTEGER NOT NULL,
    n_inserted   INTEGER NOT NULL,
    errors_json  TEXT,
    model        TEXT,
    PRIMARY KEY (paper_sha256, run_id)
);
"""

_COLS = (
    "run_id", "extracted_at", "parser_name", "skill_name",
    "n_errors", "n_extracted", "n_validated", "n_inserted", "errors_json", "model",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExtractionRunLog:
    def __init__(self, db_path: str = "palimpsest.db") -> None:
        # check_same_thread=False mirrors CostMeter: the TUI runs the agent (and
        # thus run_paper) on a worker thread. Access is serialized the same way.
        self.conn = sqlite3.connect(canonical_db(db_path), check_same_thread=False)
        self.conn.executescript(_DDL)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        # T58: add errors_json to a T57-era table that predates the column.
        # nullable, no default → ALTER backfills existing rows with NULL. Guarded
        # by table_info so reopening an already-migrated DB is a no-op.
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(extraction_runs)")}
        if "errors_json" not in cols:
            self.conn.execute("ALTER TABLE extraction_runs ADD COLUMN errors_json TEXT")
        # parser×model matrix: tag which LLM produced the run. Same ALTER-backfill
        # pattern as errors_json — nullable, so pre-matrix rows read NULL.
        if "model" not in cols:
            self.conn.execute("ALTER TABLE extraction_runs ADD COLUMN model TEXT")

    def record(
        self,
        *,
        paper_sha256: str,
        run_id: str,
        parser_name: str,
        skill_name: str,
        n_errors: int,
        n_extracted: int,
        n_validated: int,
        n_inserted: int,
        errors_json: str | None = None,
        model: str | None = None,
    ) -> None:
        # INSERT OR REPLACE: a re-run with the same run_id overwrites in place
        # (matches parser_runs' idempotent re-run semantics). errors_json is the
        # T58 per-item drop reasons (a JSON list); None for callers that only
        # track counts (T57) — kept optional so those callers are unaffected.
        # model tags the LLM (parser×model matrix); None for pre-matrix callers.
        self.conn.execute(
            "INSERT OR REPLACE INTO extraction_runs "
            "(paper_sha256, run_id, extracted_at, parser_name, skill_name, "
            " n_errors, n_extracted, n_validated, n_inserted, errors_json, model) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                paper_sha256, run_id, _now(), parser_name, skill_name,
                n_errors, n_extracted, n_validated, n_inserted, errors_json, model,
            ),
        )
        self.conn.commit()

    def latest_per_paper(self) -> dict[str, dict]:
        """Most recent run per paper as ``{sha256: {col: value}}``.

        "Most recent" = max rowid (insertion order), not max timestamp —
        extracted_at is 1s-resolution and would tie on back-to-back runs.
        """
        rows = self.conn.execute(
            f"SELECT paper_sha256, {', '.join(_COLS)} FROM extraction_runs "
            "WHERE rowid IN (SELECT MAX(rowid) FROM extraction_runs "
            "                GROUP BY paper_sha256)"
        ).fetchall()
        return {row[0]: dict(zip(_COLS, row[1:])) for row in rows}

    def latest_run(self, paper_sha256: str, parser_name: str) -> dict | None:
        """Most recent run for one (paper, parser) as ``{col: value}``, or None.

        Parser-scoped (unlike ``latest_per_paper``) because T58's
        ``extraction_report`` asks "what dropped for THIS paper under THIS
        parser" — a docling run must not shadow the mineru one. "Most recent" =
        max rowid (insertion order), matching ``latest_per_paper``.
        """
        row = self.conn.execute(
            f"SELECT {', '.join(_COLS)} FROM extraction_runs "
            "WHERE paper_sha256 = ? AND parser_name = ? "
            "ORDER BY rowid DESC LIMIT 1",
            (paper_sha256, parser_name),
        ).fetchone()
        return dict(zip(_COLS, row)) if row is not None else None
