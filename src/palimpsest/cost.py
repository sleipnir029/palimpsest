"""CostMeter: SQLite-backed €-budget ledger with a live (re-read) cap.

Every paid LLM/GPU call must check the meter first (T06 wiring). The cap is read
from the DB on every access so a concurrent `/budget` (T28) takes effect for the
next check without a restart.
"""

import sqlite3

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
    def __init__(self, db_path: str = "palimpsest.db"):
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
