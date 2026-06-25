"""Phase C — viewer matrix routes: /data (confidence+model+filter), /runs, /parse, /export.

Injects an in-memory store with two model-tagged, confidence-bearing measurements
for one paper (mirroring test_viewer_data.py's _graph_store monkeypatch), so the
new fields + parser/model filtering + the selector source are exercised offline.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from schema.generated.pydantic import Evidence, Overpotential, Paper

from palimpsest.store import RDFStore
from palimpsest.viewer import app as viewer_app

client = TestClient(viewer_app.app)

_SHA = "a" * 64


def _ev(parser: str) -> Evidence:
    return Evidence(
        paper=Paper(sha256=_SHA), page=1,
        bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
        parser_name=parser,
    )


def _store_matrix() -> RDFStore:
    """Two cells for one paper: (docling, flash, conf .9) and (mineru, gemini, conf .8)."""
    s = RDFStore()
    s.insert_extraction(
        Overpotential(value=236.0, unit_label="mV", confidence=0.9, evidence=_ev("docling")),
        run_id="r-flash", extraction_model="deepseek-v4-flash",
    )
    s.insert_extraction(
        Overpotential(value=300.0, unit_label="mV", confidence=0.8, evidence=_ev("mineru")),
        run_id="r-gem", extraction_model="gemini-3.5-flash (direct)",
    )
    return s


def test_data_carries_confidence_and_model(monkeypatch):
    monkeypatch.setattr(viewer_app, "_graph_store", _store_matrix)
    triples = client.get(f"/paper/{_SHA}/data").json()["triples"]
    assert len(triples) == 2
    by_parser = {t["parser_name"]: t for t in triples}
    assert by_parser["docling"]["confidence"] == 0.9
    assert by_parser["docling"]["model"] == "deepseek-v4-flash"
    assert by_parser["mineru"]["confidence"] == 0.8
    assert by_parser["mineru"]["model"] == "gemini-3.5-flash (direct)"


def test_data_filters_by_parser_and_model(monkeypatch):
    monkeypatch.setattr(viewer_app, "_graph_store", _store_matrix)
    only = client.get(f"/paper/{_SHA}/data",
                      params={"parser": "docling", "model": "deepseek-v4-flash"}).json()["triples"]
    assert len(only) == 1 and only[0]["value"] == 236.0
    # a cell that doesn't exist → empty
    none = client.get(f"/paper/{_SHA}/data",
                      params={"parser": "docling", "model": "gemini-3.5-flash (direct)"}).json()["triples"]
    assert none == []


def test_runs_lists_cells_with_counts(monkeypatch):
    monkeypatch.setattr(viewer_app, "_graph_store", _store_matrix)
    runs = client.get(f"/paper/{_SHA}/runs").json()["runs"]
    cells = {(r["parser"], r["model"]): r["count"] for r in runs}
    assert cells == {
        ("docling", "deepseek-v4-flash"): 1,
        ("mineru", "gemini-3.5-flash (direct)"): 1,
    }


def test_export_csv(monkeypatch):
    monkeypatch.setattr(viewer_app, "_graph_store", _store_matrix)
    r = client.get(f"/paper/{_SHA}/export", params={"format": "csv"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.splitlines()
    assert lines[0] == "measurement,slot,value,unit,confidence,page,bbox,parser,model,source_text"
    assert len(lines) == 3  # header + 2 rows
    assert "deepseek-v4-flash" in r.text and "gemini-3.5-flash (direct)" in r.text


def test_parse_route_guards(monkeypatch):
    monkeypatch.setattr(viewer_app, "_graph_store", _store_matrix)
    assert client.get(f"/paper/{_SHA}/parse/nope").status_code == 400   # unknown parser
    assert client.get("/paper/not-hex/parse/docling").status_code == 400  # bad sha
    # valid parser + valid-shape sha not in cache → 404
    assert client.get(f"/paper/{'b' * 64}/parse/docling").status_code == 404


def test_untagged_model_round_trips(monkeypatch):
    """A legacy measurement with no extraction_model must not break the queries:
    /data returns model=null and /runs yields a null-model cell with a count."""
    def _store():
        s = RDFStore()
        s.insert_extraction(
            Overpotential(value=200.0, unit_label="mV", evidence=_ev("docling")),
            run_id="r-legacy",  # no extraction_model
        )
        return s
    monkeypatch.setattr(viewer_app, "_graph_store", _store)
    triples = client.get(f"/paper/{_SHA}/data").json()["triples"]
    assert len(triples) == 1 and triples[0]["model"] is None
    # parser filter (no model param) still includes the untagged measurement
    assert len(client.get(f"/paper/{_SHA}/data", params={"parser": "docling"}).json()["triples"]) == 1
    runs = client.get(f"/paper/{_SHA}/runs").json()["runs"]
    assert runs == [{"parser": "docling", "model": None, "count": 1}]


def test_runs_counts_multiple_per_cell(monkeypatch):
    """COUNT(DISTINCT ?m) per cell must not multiply: 2 measurements in one
    (parser, model) cell → count 2 (guards the GRAPH-join row-multiplication risk)."""
    def _store():
        s = RDFStore()
        for v in (236.0, 412.0):
            s.insert_extraction(
                Overpotential(value=v, unit_label="mV", evidence=_ev("docling")),
                run_id=f"r-{v}", extraction_model="deepseek-v4-flash",
            )
        return s
    monkeypatch.setattr(viewer_app, "_graph_store", _store)
    runs = client.get(f"/paper/{_SHA}/runs").json()["runs"]
    assert runs == [{"parser": "docling", "model": "deepseek-v4-flash", "count": 2}]


def test_csv_quotes_embedded_commas(monkeypatch):
    """source_text with commas/quotes/newlines must round-trip through csv (not
    split into extra columns)."""
    import csv as _csv
    import io as _io

    def _store():
        s = RDFStore()
        ev = Evidence(
            paper=Paper(sha256=_SHA), page=1,
            bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
            parser_name="docling", source_text='a, b\n"c", 236 mV',
        )
        s.insert_extraction(
            Overpotential(value=236.0, unit_label="mV", confidence=0.9, evidence=ev),
            run_id="r1", extraction_model="deepseek-v4-flash",
        )
        return s
    monkeypatch.setattr(viewer_app, "_graph_store", _store)
    text = client.get(f"/paper/{_SHA}/export", params={"format": "csv"}).text
    rows = list(_csv.reader(_io.StringIO(text)))
    assert rows[0] == ["measurement", "slot", "value", "unit", "confidence",
                       "page", "bbox", "parser", "model", "source_text"]
    assert len(rows) == 2 and len(rows[1]) == 10           # not split by the embedded comma
    assert rows[1][9] == 'a, b\n"c", 236 mV'               # source_text intact


def test_pageinfo_paddle_and_docling(monkeypatch, tmp_path):
    """/pageinfo returns the reference page size + coord mode: docling=points (from
    .pages[].size), paddle=pixels (from .pages[].res.width/height)."""
    import json as _json
    (tmp_path / "docling.json").write_text(_json.dumps(
        {"pages": {"1": {"size": {"width": 595.0, "height": 790.0}}}}))
    (tmp_path / "paddle.json").write_text(_json.dumps(
        {"pages": [{"res": {"page_index": 0, "width": 1191, "height": 1582}}]}))

    class _Cache:
        PARSERS = viewer_app.ParserCache.PARSERS
        def get_output(self, sha, parser):
            return tmp_path / f"{parser}.json"

    monkeypatch.setattr(viewer_app, "ParserCache", _Cache)
    d = client.get(f"/paper/{_SHA}/pageinfo/docling").json()
    assert d["mode"] == "points" and d["pages"]["1"] == [595.0, 790.0]
    p = client.get(f"/paper/{_SHA}/pageinfo/paddle").json()
    assert p["mode"] == "pixels" and p["pages"]["1"] == [1191.0, 1582.0]


def test_pageinfo_mineru_none_and_guards(monkeypatch, tmp_path):
    """mineru's cached output has no page size → mode 'none'. Guards: 400 on bad
    sha / unknown parser."""
    import json as _json
    (tmp_path / "mineru.json").write_text(_json.dumps([[{"bbox": [1, 2, 3, 4], "text": "x"}]]))

    class _Cache:
        PARSERS = viewer_app.ParserCache.PARSERS
        def get_output(self, sha, parser):
            return tmp_path / f"{parser}.json"

    monkeypatch.setattr(viewer_app, "ParserCache", _Cache)
    assert client.get(f"/paper/{_SHA}/pageinfo/mineru").json()["mode"] == "none"
    assert client.get(f"/paper/{_SHA}/pageinfo/nope").status_code == 400
    assert client.get("/paper/not-hex/pageinfo/docling").status_code == 400


# ---- Parser tab (/spans) + Gold tab (/gold) — the funnel views ----

def test_spans_route_projects_parser_text(monkeypatch, tmp_path):
    """/spans runs the same per-parser adapter extraction uses (read-only, no LLM):
    one docling text element → one {page, text} span. Guards: 400 bad sha/parser, 404 uncached."""
    import json as _json
    (tmp_path / "docling.json").write_text(_json.dumps(
        {"texts": [{"text": "236 mV", "prov": [{"bbox": {"l": 1, "t": 2, "r": 3, "b": 4}, "page_no": 1}]}]}))

    class _Cache:
        PARSERS = viewer_app.ParserCache.PARSERS
        def get_output(self, sha, parser):
            p = tmp_path / f"{parser}.json"
            return p if p.exists() else None

    monkeypatch.setattr(viewer_app, "ParserCache", _Cache)
    r = client.get(f"/paper/{_SHA}/spans/docling").json()
    # bbox is carried through (native parser coords) so the viewer can highlight the region
    assert r["count"] == 1 and r["spans"] == [{"page": 1, "text": "236 mV", "bbox": [1.0, 2.0, 3.0, 4.0]}]
    assert client.get(f"/paper/{_SHA}/spans/nope").status_code == 400     # unknown parser
    assert client.get("/paper/not-hex/spans/docling").status_code == 400  # bad sha
    assert client.get(f"/paper/{_SHA}/spans/mineru").status_code == 404    # valid parser, uncached


def test_spans_route_degrades_on_misshaped_cache(monkeypatch, tmp_path):
    """A valid-JSON but wrong-shape cache file (corruption / parser format drift) must
    degrade to count 0, not 500 the read route."""
    (tmp_path / "docling.json").write_text("[]")  # docling adapter expects a dict, gets a list

    class _Cache:
        PARSERS = viewer_app.ParserCache.PARSERS
        def get_output(self, sha, parser):
            return tmp_path / f"{parser}.json"

    monkeypatch.setattr(viewer_app, "ParserCache", _Cache)
    r = client.get(f"/paper/{_SHA}/spans/docling")
    assert r.status_code == 200 and r.json()["count"] == 0


# the 2-tuple gold paper (experiments/ab_extract.py GOLD): Overpotential 210 & 330
_GOLD_SHA = "bd86866b0d0ed41bd5cbaf523aa92287194f052841092df665df5380c303be01"


def test_gold_route_matches_benchmark_scorer(monkeypatch):
    """/gold greedy-matches the cell's extracted (type,value) against GOLD[sha] using
    ab_extract's own `_matches` — so tp/recall/precision equal `_score_preds` (no drift).
    Two extracted match gold (210, 330); a third (999) is an extra (false positive)."""
    viewer_app._gold_module.cache_clear()
    _score_preds = viewer_app._gold_module()._score_preds  # the loader the endpoint uses

    def _store():
        s = RDFStore()
        for v in (210.0, 330.0, 999.0):
            s.insert_extraction(
                Overpotential(value=v, unit_label="mV",
                              evidence=Evidence(paper=Paper(sha256=_GOLD_SHA), page=1,
                                                bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
                                                parser_name="docling")),
                run_id=f"r-{v}", extraction_model="deepseek-v4-flash",
            )
        return s
    monkeypatch.setattr(viewer_app, "_graph_store", _store)
    g = client.get(f"/paper/{_GOLD_SHA}/gold").json()
    assert g["gold_total"] == 2 and g["tp"] == 2 and g["fn"] == 0 and g["fp"] == 1
    assert g["recall"] == 1.0
    assert all(x["matched"] for x in g["gold"])
    assert [x["matched"] for x in g["extracted"]].count(False) == 1  # the 999

    # identical numbers to the benchmark scorer on the same inputs
    preds = [(x["type"], x["value"]) for x in g["extracted"]]
    tp, n, recall, prec = _score_preds(preds, [("Overpotential", 210.0), ("Overpotential", 330.0)])
    assert (g["tp"], g["recall"], g["precision"]) == (tp, recall, prec)


def test_gold_route_duplicate_preds_dont_double_claim(monkeypatch):
    """Greedy semantics: two extractions of the SAME value can't both claim one gold
    tuple. preds [210, 210] vs gold [210, 330] → tp=1 (one 210 matches), fp=1 (the
    second 210 is extra), fn=1 (330 missed). Locks the matched-set tracking."""
    def _store():
        s = RDFStore()
        for rid in ("a", "b"):  # two distinct measurements, same value 210
            s.insert_extraction(
                Overpotential(value=210.0, unit_label="mV",
                              evidence=Evidence(paper=Paper(sha256=_GOLD_SHA), page=1,
                                                bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
                                                parser_name="docling")),
                run_id=f"r-{rid}", extraction_model="deepseek-v4-flash",
            )
        return s
    monkeypatch.setattr(viewer_app, "_graph_store", _store)
    g = client.get(f"/paper/{_GOLD_SHA}/gold").json()
    assert (g["tp"], g["fp"], g["fn"]) == (1, 1, 1)
    assert [x["matched"] for x in g["extracted"]].count(True) == 1  # only one 210 claims gold


def test_gold_route_no_gold_for_unknown_sha(monkeypatch):
    monkeypatch.setattr(viewer_app, "_graph_store", _store_matrix)
    g = client.get(f"/paper/{_SHA}/gold").json()  # _SHA="a"*64 is not in GOLD
    assert g["gold_total"] == 0 and g["gold"] == []


def test_gold_module_absent_is_graceful(monkeypatch, tmp_path):
    """No experiments/ on disk (installed package without the repo) → _gold_module()
    returns None instead of raising, so the Gold tab degrades to 'no gold'."""
    monkeypatch.chdir(tmp_path)
    viewer_app._gold_module.cache_clear()
    try:
        assert viewer_app._gold_module() is None
    finally:
        viewer_app._gold_module.cache_clear()  # don't leak the empty load to other tests


def test_data_passes_unit_verbatim_for_client_escaping(monkeypatch):
    """The /data endpoint is a passthrough: a malicious unit_label is returned
    verbatim (the server does NOT sanitize — the viewer escapes it client-side).
    Documents the trust boundary so the client-side escaping can't silently regress
    into a server expectation."""
    payload = '<img src=x onerror=alert(1)>'

    def _store():
        s = RDFStore()
        s.insert_extraction(
            Overpotential(value=1.0, unit_label=payload, evidence=_ev("docling")),
            run_id="r-xss", extraction_model="deepseek-v4-flash",
        )
        return s
    monkeypatch.setattr(viewer_app, "_graph_store", _store)
    assert client.get(f"/paper/{_SHA}/data").json()["triples"][0]["unit"] == payload
