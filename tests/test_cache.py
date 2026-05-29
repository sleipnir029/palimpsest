"""T15 tests. Pure SQLite + filesystem, no network, no GPU.

Covers the parse-once cache surface: add a paper, insert per-parser runs,
detect completion against the T17 5-parser set, resolve cached output paths
(file or directory), and filter a corpus down to PDFs that still need work.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import fitz
import pytest

from palimpsest.cache import ParserCache

SHA_A = "a" * 64
SHA_B = "b" * 64


def _mk(tmp_path: Path) -> ParserCache:
    return ParserCache(
        db_path=str(tmp_path / "p.db"),
        cache_dir=tmp_path / "cache",
    )


def _insert_run(
    cache: ParserCache,
    sha: str,
    parser: str,
    output_path: str = "out.json",
    parser_ver: str = "0.1.0",
) -> None:
    cache.insert_parser_run(
        sha256=sha,
        parser_name=parser,
        parser_ver=parser_ver,
        output_path=output_path,
        gpu_seconds=12.5,
        gpu_cost_eur=0.04,
        run_id="run-x",
    )


def _make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def test_add_paper_and_insert_runs_completes_set(tmp_path):
    cache = _mk(tmp_path)
    cache.add_paper(SHA_A, "foo.pdf", page_count=12)
    for parser in ParserCache.PARSERS:
        _insert_run(cache, SHA_A, parser, output_path=f"{parser}.json")
    assert cache.has_all_parsers(SHA_A) is True


def test_has_all_parsers_partial_returns_false(tmp_path):
    cache = _mk(tmp_path)
    cache.add_paper(SHA_A, "foo.pdf", page_count=1)
    # 4 of 5 — missing 'paddle'
    for parser in ("docling", "mineru", "chandra", "dots"):
        _insert_run(cache, SHA_A, parser)
    assert cache.has_all_parsers(SHA_A) is False


def test_get_output_returns_correct_path(tmp_path):
    cache = _mk(tmp_path)
    cache.add_paper(SHA_A, "foo.pdf", page_count=1)
    # Touch the blob the row points at.
    blob = cache.cache_dir / "docling.json"
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_text("{}")
    _insert_run(cache, SHA_A, "docling", output_path="docling.json")
    got = cache.get_output(SHA_A, "docling")
    assert got is not None
    assert got == blob
    assert got.exists()


def test_get_output_returns_none_when_blob_missing(tmp_path):
    cache = _mk(tmp_path)
    cache.add_paper(SHA_A, "foo.pdf", page_count=1)
    _insert_run(cache, SHA_A, "docling", output_path="docling.json")
    # No file ever touched on disk.
    assert cache.get_output(SHA_A, "docling") is None
    # Unknown parser for this paper → also None.
    assert cache.get_output(SHA_A, "mineru") is None


def test_list_unseen_filters_cached(tmp_path):
    cache = _mk(tmp_path)
    p_done = tmp_path / "done.pdf"
    p_todo = tmp_path / "todo.pdf"
    _make_pdf(p_done, "done")
    _make_pdf(p_todo, "todo")

    # Hash p_done the same way list_unseen will, then fully cache it.
    from palimpsest.tools.read_paper import read_paper
    sha_done = read_paper(str(p_done))["sha256"]
    cache.add_paper(sha_done, "done.pdf", page_count=1)
    for parser in ParserCache.PARSERS:
        _insert_run(cache, sha_done, parser)

    unseen = cache.list_unseen([p_done, p_todo])
    assert len(unseen) == 1
    path, sha = unseen[0]
    assert path == p_todo
    assert len(sha) == 64


def test_check_constraint_rejects_unknown_parser(tmp_path):
    cache = _mk(tmp_path)
    cache.add_paper(SHA_A, "foo.pdf", page_count=1)
    # match= so the test fails for the right reason — both CHECK and FK raise
    # sqlite3.IntegrityError, and the parser_name is satisfied by add_paper above.
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert_run(cache, SHA_A, "olmocr")  # dropped in T17


def test_fk_rejects_orphan_parser_run(tmp_path):
    # No add_paper call for SHA_B → FK should fire.
    cache = _mk(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        _insert_run(cache, SHA_B, "docling")


def test_has_all_parsers_uses_distinct_parser_names(tmp_path):
    # Two parser_ver rows for one parser must not inflate the count past the
    # other 4 distinct parsers (the DISTINCT in has_all_parsers exists for this).
    cache = _mk(tmp_path)
    cache.add_paper(SHA_A, "foo.pdf", page_count=1)
    _insert_run(cache, SHA_A, "docling", parser_ver="0.1.0")
    _insert_run(cache, SHA_A, "docling", parser_ver="0.2.0")
    for parser in ("mineru", "chandra", "dots"):  # 4 distinct, missing 'paddle'
        _insert_run(cache, SHA_A, parser)
    assert cache.has_all_parsers(SHA_A) is False


def test_insert_or_replace_updates_same_key(tmp_path):
    # T16 will re-run a parser on the same (sha, parser, parser_ver) — confirm
    # the row is overwritten in place and get_output returns the new path.
    cache = _mk(tmp_path)
    cache.add_paper(SHA_A, "foo.pdf", page_count=1)
    (cache.cache_dir / "v1.json").parent.mkdir(parents=True, exist_ok=True)
    (cache.cache_dir / "v1.json").write_text("{}")
    (cache.cache_dir / "v2.json").write_text("{}")
    _insert_run(cache, SHA_A, "docling", output_path="v1.json")
    _insert_run(cache, SHA_A, "docling", output_path="v2.json")
    assert cache.get_output(SHA_A, "docling") == cache.cache_dir / "v2.json"
