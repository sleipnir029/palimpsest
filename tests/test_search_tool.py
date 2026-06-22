"""B3: the `search` tool — regex over workspace text files, read-only.

Key invariant: it must NOT surface secret-file content (.env/config.txt/*.key),
mirroring the session transcript's redaction discipline (policy.is_secret_path).
"""

from __future__ import annotations

import pytest

from palimpsest.tools.search import search


@pytest.fixture(autouse=True)
def _isolate_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))


def test_search_finds_matches(tmp_path):
    (tmp_path / "notes.md").write_text("alpha\nbeta here\ngamma\n", encoding="utf-8")
    out = search("beta")
    assert "notes.md:2:" in out
    assert "beta here" in out


def test_search_skips_secret_files(tmp_path):
    (tmp_path / ".env").write_text("API_KEY=topsecret\n", encoding="utf-8")
    (tmp_path / "ok.txt").write_text("mentions API_KEY in prose\n", encoding="utf-8")
    out = search("API_KEY")
    assert "topsecret" not in out      # .env content never surfaced
    assert "ok.txt" in out             # a non-secret match is still returned


def test_search_no_matches(tmp_path):
    (tmp_path / "a.txt").write_text("nothing relevant\n", encoding="utf-8")
    assert search("zzz") == "(no matches)"


def test_search_bad_regex(tmp_path):
    assert search("(").startswith("error: bad regex")


def test_search_rejects_path_outside_workspace(tmp_path):
    assert "outside the workspace" in search("x", path="../..")
