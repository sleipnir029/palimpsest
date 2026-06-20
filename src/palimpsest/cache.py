"""ParserCache: SQLite-backed parse-once cache (T15).

Keyed by (sha256, parser_name, parser_ver). One row per parser run; output blobs
live under `cache_dir` and are referenced by a relative `output_path` (file or
directory — T16 owns the convention per parser).

Parser set is the T17 5-parser set (docling, mineru, chandra, dots, paddle);
the T15 card's 4-parser set (with olmocr) is superseded by PROGRESS T17 and
logged in DEVIATIONS.md.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .cost import canonical_db  # one repo-root palimpsest.db, cwd-independent
from pathlib import Path

from .tools.read_paper import read_paper

_DDL = """
CREATE TABLE IF NOT EXISTS papers (
    sha256     TEXT PRIMARY KEY,
    filename   TEXT NOT NULL,
    added_at   TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    doi        TEXT
);
CREATE TABLE IF NOT EXISTS parser_runs (
    paper_sha256 TEXT NOT NULL,
    parser_name  TEXT NOT NULL
                   CHECK (parser_name IN
                          ('docling','mineru','chandra','dots','paddle')),
    parser_ver   TEXT NOT NULL,
    parsed_at    TEXT NOT NULL,
    output_path  TEXT NOT NULL,
    gpu_seconds  REAL NOT NULL,
    gpu_cost_eur REAL NOT NULL,
    run_id       TEXT NOT NULL,
    PRIMARY KEY (paper_sha256, parser_name, parser_ver),
    FOREIGN KEY (paper_sha256) REFERENCES papers(sha256)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ParserCache:
    PARSERS = ("docling", "mineru", "chandra", "dots", "paddle")

    def __init__(
        self,
        db_path: str = "palimpsest.db",
        cache_dir: Path = Path("cache"),
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.conn = sqlite3.connect(canonical_db(db_path))
        # SQLite defaults foreign_keys=OFF per connection — without this the
        # FOREIGN KEY clause in _DDL is documentation, not enforcement.
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_DDL)
        self.conn.commit()

    def add_paper(
        self,
        sha256: str,
        filename: str,
        page_count: int,
        doi: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO papers "
            "(sha256, filename, added_at, page_count, doi) "
            "VALUES (?, ?, ?, ?, ?)",
            (sha256, filename, _now(), page_count, doi),
        )
        self.conn.commit()

    def has_all_parsers(self, sha256: str) -> bool:
        placeholders = ",".join("?" * len(self.PARSERS))
        row = self.conn.execute(
            f"SELECT COUNT(DISTINCT parser_name) FROM parser_runs "
            f"WHERE paper_sha256 = ? AND parser_name IN ({placeholders})",
            (sha256, *self.PARSERS),
        ).fetchone()
        return int(row[0]) == len(self.PARSERS)

    def get_output(self, sha256: str, parser_name: str) -> Path | None:
        row = self.conn.execute(
            "SELECT output_path FROM parser_runs "
            "WHERE paper_sha256 = ? AND parser_name = ? "
            "ORDER BY parsed_at DESC LIMIT 1",
            (sha256, parser_name),
        ).fetchone()
        if row is None:
            return None
        path = self.cache_dir / row[0]
        # A row whose blob has been deleted is a cache miss, not a stale hit.
        return path if path.exists() else None

    def insert_parser_run(
        self,
        sha256: str,
        parser_name: str,
        parser_ver: str,
        output_path: str,
        gpu_seconds: float,
        gpu_cost_eur: float,
        run_id: str,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO parser_runs "
            "(paper_sha256, parser_name, parser_ver, parsed_at, "
            " output_path, gpu_seconds, gpu_cost_eur, run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sha256,
                parser_name,
                parser_ver,
                _now(),
                output_path,
                gpu_seconds,
                gpu_cost_eur,
                run_id,
            ),
        )
        self.conn.commit()

    def list_all_papers(self) -> list[str]:
        # Every registered paper's sha256, regardless of parse completeness.
        return [
            row[0]
            for row in self.conn.execute("SELECT sha256 FROM papers").fetchall()
        ]

    def list_unseen(self, pdfs: list[Path]) -> list[tuple[Path, str]]:
        # Use T07's read_paper so the cache key agrees with the rest of the
        # pipeline by construction (single hashing path).
        out: list[tuple[Path, str]] = []
        for p in pdfs:
            sha = read_paper(str(p))["sha256"]
            if not self.has_all_parsers(sha):
                out.append((p, sha))
        return out
