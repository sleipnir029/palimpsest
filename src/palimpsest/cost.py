"""CostMeter: SQLite-backed €-budget ledger with a live (re-read) cap.

Every paid LLM/GPU call must check the meter first (T06 wiring). The cap is read
from the DB on every access so a concurrent `/budget` (T28) takes effect for the
next check without a restart.
"""

import sqlite3
from pathlib import Path

# The ONE canonical DB: repo-root/palimpsest.db, resolved absolutely. This single file
# holds the cost ledger, the parser cache (T16), AND the extraction-run log (T57), so
# ALL of them must resolve here regardless of launch cwd — else a subdir run forks a
# second, empty file that both under-counts the €50 cap and re-parses (GPU spend,
# violating parse-once). Tests pass absolute tmp paths → untouched.
_CANONICAL_DB = str(Path(__file__).resolve().parents[2] / "palimpsest.db")


def canonical_db(db_path: str) -> str:
    """Redirect the bare relative ``"palimpsest.db"`` to the one repo-root file.

    Shared by CostMeter, ParserCache, and ExtractionRunLog so every consumer of
    palimpsest.db agrees on its location. Anything else (absolute paths, alternate
    names) passes through unchanged.
    """
    return _CANONICAL_DB if db_path == "palimpsest.db" else db_path


_DDL = """
CREATE TABLE IF NOT EXISTS cost_ledger (
    ts         TEXT DEFAULT CURRENT_TIMESTAMP,
    kind       TEXT CHECK (kind IN ('llm', 'gpu')),
    provider   TEXT,
    amount_eur REAL,
    detail     TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class BudgetExceeded(Exception):
    def __init__(self, spent: float, cap: float, projected: float):
        self.spent = spent
        self.cap = cap
        self.projected = projected
        super().__init__(
            f"budget exceeded: spent €{spent:.2f} + projected €{projected:.2f} "
            f"> cap €{cap:.2f}"
        )


class CostMeter:
    def __init__(self, db_path: str = _CANONICAL_DB):
        # Redirect the bare relative default to the canonical repo-root ledger so every
        # runtime entry point (pipeline/agent/run_paper/tui/parse_corpus/llm_matrix)
        # shares ONE budget, regardless of launch cwd. Absolute paths (tests) pass through.
        db_path = canonical_db(db_path)
        self.db_path = db_path  # resolved path (post-redirect); handy for debug + tests
        # check_same_thread=False so the TUI's thread worker (T26) can record from
        # off the main thread. The caller MUST serialize access — the TUI relies on
        # single-in-flight (input disabled while running) + call_from_thread, so the
        # connection is never touched concurrently. Add a threading.Lock here if a
        # concurrent reader is ever introduced (e.g. a timer-based live cost bar).
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.executescript(_DDL)
        self.conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('budget_eur', '50')"
        )
        self.conn.commit()

    @property
    def cap(self) -> float:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = 'budget_eur'"
        ).fetchone()
        return float(row[0])

    def soft(self) -> float:
        return 0.8 * self.cap

    def total_eur(self) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_eur), 0) FROM cost_ledger"
        ).fetchone()
        return float(row[0])

    def check_or_raise(self, projected_eur: float) -> None:
        spent = self.total_eur()
        cap = self.cap
        if spent + projected_eur > cap:
            raise BudgetExceeded(spent, cap, projected_eur)

    def record_llm(self, provider: str, eur: float, detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO cost_ledger (kind, provider, amount_eur, detail) "
            "VALUES ('llm', ?, ?, ?)",
            (provider, eur, detail),
        )
        self.conn.commit()

    def record_gpu(self, eur: float, detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO cost_ledger (kind, provider, amount_eur, detail) "
            "VALUES ('gpu', NULL, ?, ?)",
            (eur, detail),
        )
        self.conn.commit()

    def set_budget(self, new_cap: int) -> str:
        spent = self.total_eur()
        if new_cap < spent:
            return (
                f"refused: new cap €{new_cap} is below current spend €{spent:.2f}"
            )
        self.conn.execute(
            "UPDATE settings SET value = ? WHERE key = 'budget_eur'", (str(new_cap),)
        )
        self.conn.commit()
        return f"budget set to €{new_cap}"
