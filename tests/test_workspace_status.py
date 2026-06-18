"""T57 — workspace_status tests. Pure SQLite + in-memory graph, no network, €0.

Builds a synthetic ParserCache + a seeded in-memory RDFStore + an ExtractionRunLog
and asserts the one-call orientation summary reports, per paper: PDFs present,
which parsers have run, how many measurements reached the graph, a real
dropped-count teaser (from the recorded run), and what's pending.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from schema.generated.pydantic import Condition, Evidence, Overpotential, Paper

from palimpsest.cache import ParserCache
from palimpsest.runs import ExtractionRunLog
from palimpsest.store import RDFStore
from palimpsest.tools.workspace_status import workspace_status

SHA_A = "a" * 64
SHA_B = "b" * 64


def _seed_cache(tmp_path: Path) -> ParserCache:
    cache = ParserCache(db_path=str(tmp_path / "p.db"), cache_dir=tmp_path / "cache")
    cache.add_paper(SHA_A, "alpha.pdf", page_count=12)
    cache.add_paper(SHA_B, "beta.pdf", page_count=8)
    for parser in ParserCache.PARSERS:  # alpha fully parsed (5/5)
        cache.insert_parser_run(SHA_A, parser, "0.2.2", f"{parser}.json", 1.0, 0.01, "r")
    for parser in ("docling", "mineru"):  # beta partially parsed (2/5)
        cache.insert_parser_run(SHA_B, parser, "0.2.2", f"{parser}.json", 1.0, 0.01, "r")
    return cache


def _measurement(sha: str, value: float) -> Overpotential:
    return Overpotential(
        value=value, unit_label="mV",
        condition=Condition(current_density=10.0),
        evidence=Evidence(
            paper=Paper(sha256=sha), page=2,
            bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
            parser_name="mineru", source_text="η = ...",
        ),
    )


def _empty_dir(tmp_path: Path) -> str:
    d = tmp_path / "papers"
    d.mkdir()
    return str(d)


def test_reports_papers_parse_and_extract_state(tmp_path):
    cache = _seed_cache(tmp_path)
    store = RDFStore()
    store.insert_extraction(_measurement(SHA_A, 236.0), run_id="r1")
    store.insert_extraction(_measurement(SHA_A, 298.0), run_id="r1")  # 2 in graph for alpha
    log = ExtractionRunLog(str(tmp_path / "runs.db"))

    out = workspace_status(_empty_dir(tmp_path), cache=cache, store=store, run_log=log)

    assert "alpha.pdf" in out and "beta.pdf" in out
    # alpha: fully parsed, 2 measurements extracted
    assert "5/5" in out
    assert "2 measurements" in out
    # beta: partially parsed, nothing extracted yet
    assert "2/5" in out
    assert "needs extraction" in out


def test_dropped_count_teaser_from_recorded_run(tmp_path):
    cache = _seed_cache(tmp_path)
    store = RDFStore()
    store.insert_extraction(_measurement(SHA_A, 236.0), run_id="r1")
    store.insert_extraction(_measurement(SHA_A, 298.0), run_id="r1")
    log = ExtractionRunLog(str(tmp_path / "runs.db"))
    # 5 valid + 3 errors = 8 candidates; 2 reached the graph → 6 dropped.
    log.record(
        paper_sha256=SHA_A, run_id="r1", parser_name="mineru",
        skill_name="oer-extraction",
        n_errors=3, n_extracted=5, n_validated=4, n_inserted=2,
    )

    out = workspace_status(_empty_dir(tmp_path), cache=cache, store=store, run_log=log)

    assert "8 found" in out
    assert "2 inserted" in out
    assert "6 dropped" in out
    assert "T58" in out  # pointer to the full per-item reasons


def test_graph_without_run_metadata_notes_the_gap(tmp_path):
    """A paper with measurements in the graph but no recorded run (e.g. inserted
    by a pre-T57 demo run) reports the graph count honestly and flags that no
    drop count is available — never fabricates one."""
    cache = _seed_cache(tmp_path)
    store = RDFStore()
    store.insert_extraction(_measurement(SHA_A, 236.0), run_id="r1")
    log = ExtractionRunLog(str(tmp_path / "runs.db"))  # empty — no record() call

    out = workspace_status(_empty_dir(tmp_path), cache=cache, store=store, run_log=log)

    assert "1 measurements" in out
    assert "no run metadata" in out


def test_unregistered_disk_pdf_flagged_needs_parsing(tmp_path):
    cache = ParserCache(db_path=str(tmp_path / "p.db"), cache_dir=tmp_path / "cache")
    papers = tmp_path / "papers"
    papers.mkdir()
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "fresh paper")
    doc.save(str(papers / "fresh.pdf"))
    doc.close()

    out = workspace_status(str(papers), cache=cache, store=RDFStore(),
                           run_log=ExtractionRunLog(str(tmp_path / "runs.db")))

    assert "fresh.pdf" in out
    assert "needs parsing" in out


def test_registered_paper_with_no_parsers_needs_parsing(tmp_path):
    """A paper added to the cache but never parsed (0 parser_runs) reports
    'needs parsing' — the registered-but-unparsed branch, distinct from a loose
    on-disk PDF."""
    cache = ParserCache(db_path=str(tmp_path / "p.db"), cache_dir=tmp_path / "cache")
    cache.add_paper(SHA_A, "gamma.pdf", page_count=5)  # no insert_parser_run

    out = workspace_status(_empty_dir(tmp_path), cache=cache, store=RDFStore(),
                           run_log=ExtractionRunLog(str(tmp_path / "runs.db")))

    assert "gamma.pdf" in out
    assert "0/5" in out
    assert "needs parsing" in out


def test_empty_workspace(tmp_path):
    cache = ParserCache(db_path=str(tmp_path / "p.db"), cache_dir=tmp_path / "cache")
    out = workspace_status(_empty_dir(tmp_path), cache=cache, store=RDFStore(),
                           run_log=ExtractionRunLog(str(tmp_path / "runs.db")))
    assert "no papers" in out.lower()
