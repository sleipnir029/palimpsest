"""Offline tests for the agentic tool layer (Phase 1) + the agent factory.

Covers the new perception/query/pipeline tools (read_file, list_dir,
sparql_query, extract_paper) and the dynamic system-prompt / build_agent factory
that replaced the duplicated construction in __main__.py and tui/app.py.
"""

from __future__ import annotations

import json

from palimpsest.agent import build_agent, build_system_prompt
from palimpsest.tools import TOOLS
from palimpsest.tools.list_dir import list_dir
from palimpsest.tools.read_file import _MAX_CHARS, read_file


# --- read_file --------------------------------------------------------------

def test_read_file_returns_contents(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("hello palimpsest", encoding="utf-8")
    assert read_file(str(f)) == "hello palimpsest"


def test_read_file_truncates_large_file(tmp_path):
    f = tmp_path / "big.json"
    f.write_text("x" * (_MAX_CHARS + 500), encoding="utf-8")
    out = read_file(str(f))
    assert out.startswith("x" * _MAX_CHARS)        # exact first _MAX_CHARS, no off-by-one
    assert out[_MAX_CHARS] == "\n"                  # marker begins right after the cap
    assert f"is {_MAX_CHARS + 500} chars" in out    # true length reported


def test_read_file_refuses_binary(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.7\x00\x00 binary junk")
    assert "binary file" in read_file(str(f))


# --- list_dir ---------------------------------------------------------------

def test_list_dir_marks_subdirs(tmp_path):
    (tmp_path / "papers").mkdir()
    (tmp_path / "a.pdf").write_text("", encoding="utf-8")
    out = list_dir(str(tmp_path)).splitlines()
    assert "papers/" in out and "a.pdf" in out


def test_list_dir_rejects_non_directory(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("", encoding="utf-8")
    assert "not a directory" in list_dir(str(f))


def test_list_dir_empty(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    assert list_dir(str(d)) == "(empty)"


# --- sparql_query (store monkeypatched) -------------------------------------

def test_sparql_query_returns_json_rows(monkeypatch):
    import palimpsest.store as store_mod

    class _FakeStore:
        def __init__(self, path):  # signature must accept the "store" path
            assert path == "store"

        def sparql(self, query):
            assert "SELECT" in query
            return [{"v": 236.0, "unit": "mV"}]

    monkeypatch.setattr(store_mod, "RDFStore", _FakeStore)
    from palimpsest.tools.sparql_query import sparql_query

    rows = json.loads(sparql_query("SELECT ?v ?unit WHERE { ?m ?p ?v }"))
    assert rows == [{"v": 236.0, "unit": "mV"}]


# --- extract_paper (pipeline + deps monkeypatched, no spend) -----------------

def test_extract_paper_wires_on_disk_store_and_meter(monkeypatch):
    import palimpsest.cost as cost_mod
    import palimpsest.pipeline as pipeline_mod
    import palimpsest.store as store_mod

    seen = {}

    def _fake_run_paper(pdf_path, parser_name, skill_name, *, store, cost_meter):
        seen.update(pdf=pdf_path, parser=parser_name, skill=skill_name,
                    store=store, meter=cost_meter)
        return {"paper_sha": "abc", "n_extracted": 3, "n_validated": 3, "n_inserted": 3}

    monkeypatch.setattr(pipeline_mod, "run_paper", _fake_run_paper)
    monkeypatch.setattr(store_mod, "RDFStore", lambda path: f"store@{path}")
    monkeypatch.setattr(cost_mod, "CostMeter", lambda path: f"meter@{path}")
    from palimpsest.tools.run_paper import extract_paper

    out = json.loads(extract_paper("papers/x.pdf", parser_name="docling"))
    assert out["n_inserted"] == 3
    assert seen["parser"] == "docling" and seen["skill"] == "oer-extraction"
    assert seen["store"] == "store@store"      # on-disk graph the viewer reads
    assert seen["meter"] == "meter@palimpsest.db"  # shared €50 ledger


# --- factory ----------------------------------------------------------------

class _StubMeter:
    def total_eur(self):
        return 1.23

    cap = 50.0


def test_build_system_prompt_advertises_tools_and_skills():
    p = build_system_prompt(_StubMeter())
    for name in ("read_file", "sparql_query", "extract_paper", "open_notebook"):
        assert name in p
    assert "oer-extraction" in p          # skill manifest injected
    assert "€1.23 of €50" in p            # live budget snapshot
    assert "workspace" in p               # constrained-autonomy: workspace model
    assert "never hand-edit the graph" in p  # provenance/budget invariant stated


def test_reload_skills_tool_is_registered():
    assert "reload_skills" in TOOLS


def test_build_agent_uses_full_registry_and_dynamic_prompt(tmp_path):
    from palimpsest.cost import CostMeter

    meter = CostMeter(str(tmp_path / "t.db"))
    agent = build_agent(provider=object(), cost_meter=meter)
    assert set(agent.tools) == set(TOOLS)            # every registered tool advertised
    assert "## Tools" in agent.system_prompt          # built via build_system_prompt
    assert "extract_paper" in agent.system_prompt
