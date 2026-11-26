"""Bring-your-own-agent extraction: prompt out, answer in, same gates + provenance.

Uses the bundled CC BY sample paper and its shipped parses (cache/), no LLM, no GPU.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

from palimpsest import external
from palimpsest.external import ingest, render_prompt
from palimpsest.store import RDFStore
from palimpsest.tools import extract as extract_mod

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"
_SHIPPED = Path("cache/3432d04920eb6649d15d8883e64dc7f3d54700ecd5050d09e31ae286f1d4f53d/docling.json")

pytestmark = pytest.mark.skipif(not _SHIPPED.exists(), reason="shipped docling cache absent")


def _db(tmp_path) -> str:
    return str(tmp_path / "p.db")


def _span_id(prompt: str, needle: str) -> int:
    for line in prompt.splitlines():
        m = re.match(r"\[(\d+)\] \(p\d+\) (.*)", line)
        if m and needle in m.group(2):
            return int(m.group(1))
    raise AssertionError(f"no span containing {needle!r}")


def test_prompt_is_exactly_what_extract_sends(tmp_path):
    prompt = render_prompt(FIXTURE, parser_name="docling", db_path=_db(tmp_path))
    system = prompt.split("<<<SYSTEM>>>\n", 1)[1].split("\n\n<<<USER>>>\n", 1)[0]
    user = prompt.split("<<<USER>>>\n", 1)[1]
    cap = external._Capture()
    extract_mod.extract(external.read_paper(str(FIXTURE))["sha256"], "docling",
                        "oer-extraction", provider=cap)
    assert (system, user) == (cap.calls[0][0], cap.calls[0][1] + "\n")
    assert user.rstrip().endswith("Return the measurements.")


def test_prompt_header_binds_parser_and_skill(tmp_path):
    prompt = render_prompt(FIXTURE, parser_name="mineru", db_path=_db(tmp_path))
    assert f"ingest {FIXTURE} --parser mineru --skill oer-extraction --response" in prompt


def test_prompt_refuses_unknown_or_uncached_parser(tmp_path):
    with pytest.raises(ValueError, match="parser must be one of"):
        render_prompt(FIXTURE, parser_name="chandra", db_path=_db(tmp_path))
    blank = tmp_path / "blank.pdf"
    import fitz
    doc = fitz.open()
    doc.new_page()
    doc.save(str(blank))
    with pytest.raises(FileNotFoundError, match="no cached docling parse"):
        render_prompt(blank, db_path=_db(tmp_path))


def test_prompt_refuses_multi_batch_paper(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "_MAX_PROJECTION_TOKENS", 10)
    with pytest.raises(RuntimeError, match="prompts"):
        render_prompt(FIXTURE, db_path=_db(tmp_path))


def test_ingest_gates_provenance_and_zero_cost(tmp_path):
    prompt = render_prompt(FIXTURE, parser_name="docling", db_path=_db(tmp_path))
    sid = _span_id(prompt, "236")
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({"items": [
        {"type": "Overpotential", "value": 236.0, "unit_label": "mV", "evidence": {"spans": [sid]}},
        # cites a span that does not contain the digits → must be dropped by the gate
        {"type": "Overpotential", "value": 999.0, "unit_label": "mV", "evidence": {"spans": [sid]}},
    ]}), encoding="utf-8-sig")  # BOM must not lose the answer
    store = RDFStore()

    summary = ingest(FIXTURE, answer, parser_name="docling", store=store, db_path=_db(tmp_path))

    assert summary["n_inserted"] == 1
    rows = list(store._store.query(
        "PREFIX palim: <https://w3id.org/palimpsest/> "
        "PREFIX prov: <http://www.w3.org/ns/prov#> "
        "SELECT ?page ?parser ?model WHERE { "
        "?m prov:hadPrimarySource ?e ; palim:extractionModel ?model . "
        "?e palim:page ?page ; palim:parserName ?parser . }",
        use_default_graph_as_union=True))
    assert len(rows) == 1
    assert rows[0]["parser"].value == "docling"
    assert rows[0]["model"].value == "external-agent"
    cited_page = int(re.search(rf"^\[{sid}\] \(p(\d+)\)", prompt, re.M).group(1))
    assert int(rows[0]["page"].value) == cited_page  # page comes from the cited span
    con = sqlite3.connect(_db(tmp_path))
    errs = con.execute("SELECT errors_json FROM extraction_runs").fetchone()[0]
    assert "999" in errs
    cost = con.execute("SELECT provider, amount_eur FROM cost_ledger").fetchall()
    assert cost == [("external-agent", 0.0)]


def test_ingest_prose_answer_inserts_nothing(tmp_path):
    answer = tmp_path / "answer.json"
    answer.write_text("Here are the measurements I found: 236 mV.")
    summary = ingest(FIXTURE, answer, store=RDFStore(), db_path=_db(tmp_path))
    assert summary["n_inserted"] == 0


def test_cli_ingest_prints_drop_reasons(tmp_path, monkeypatch, capsys):
    prompt = render_prompt(FIXTURE, db_path=_db(tmp_path))
    sid = _span_id(prompt, "236")
    answer = tmp_path / "a.json"
    answer.write_text(json.dumps({"items": [
        {"type": "Overpotential", "value": 999.0, "unit_label": "mV", "evidence": {"spans": [sid]}},
    ]}))
    monkeypatch.setattr(external, "ingest",
                        lambda pdf, resp, parser, skill: ingest(
                            pdf, resp, parser, skill, store=RDFStore(), db_path=_db(tmp_path)))
    from palimpsest.tools import extraction_report as er
    from palimpsest.runs import ExtractionRunLog
    real = er.extraction_report
    monkeypatch.setattr(er, "extraction_report",
                        lambda paper, parser: real(paper, parser,
                                                   run_log=ExtractionRunLog(_db(tmp_path))))
    monkeypatch.setattr(sys, "argv", ["palimpsest", "ingest", str(FIXTURE),
                                      "--response", str(answer)])
    from palimpsest.__main__ import main
    main()
    out = capsys.readouterr().out
    assert "'n_inserted': 0" in out
    assert "999" in out
