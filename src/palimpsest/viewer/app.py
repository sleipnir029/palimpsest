"""FastAPI provenance viewer (T29 skeleton).

Two-pane page: PDF on the left (rendered by vendored PDF.js), extracted data on
the right (empty placeholder — T30 populates it, T31 adds bbox hover highlight).

PDF location is content-addressed: the `papers` table stores an unreliable
`filename` (fixture rows say 'sample.pdf'), so we resolve a sha256 -> path index
by hashing every `papers/*.pdf` with T07's `read_paper`. The bytes served for
`{sha}` therefore hash to exactly `{sha}` — provenance holds by construction.

WS1: the viewer is now read-MOSTLY. It has exactly one non-GET route,
`POST /paper/{sha}/correct`, which appends an *append-only superseding* correction
via the shared `corrections.correct_measurement` primitive (reusing this process's
already-open, single-writer RocksDB store). The original triple is never mutated;
`GET /paper/{sha}/corrections` lists the recorded corrections (= labeled extractor
errors) for the data pane.
"""

from __future__ import annotations

import csv
import html
import importlib.util
import inspect
import io
import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from schema.generated import pydantic as _schema  # PEP 420 namespace pkg

from ..cache import ParserCache
from ..corrections import CorrectionError, correct_measurement
from ..cost import canonical_db
from ..store import PALIM, RDFStore, _expand
from ..tools.extract import _load_spans
from ..tools.read_paper import read_paper

_BASE = Path(__file__).parent
PAPERS_DIR = Path("papers")
DB_PATH = canonical_db("palimpsest.db")  # one repo-root ledger/cache, cwd-independent
STORE_PATH = "store"  # RocksDB dir the pipeline persists the graph to (gitignored).
# Note: RocksDB is single-writer/exclusive — the viewer holds this open for its
# lifetime (see _graph_store), so a pipeline run can't write store/ while it's up.
_SHA_RE = re.compile(r"^[0-9a-fA-F]+$")

app = FastAPI(title="palimpsest viewer")
app.mount("/static", StaticFiles(directory=_BASE / "static"), name="static")
templates = Jinja2Templates(directory=str(_BASE / "templates"))


@lru_cache(maxsize=1)
def _pdf_index() -> dict[str, Path]:
    """sha256 -> PDF path by hashing every papers/*.pdf (single T07 hashing path)."""
    index: dict[str, Path] = {}
    for pdf in sorted(PAPERS_DIR.glob("*.pdf")):
        try:
            index[read_paper(str(pdf))["sha256"]] = pdf
        except Exception:
            # One unreadable file must not 500 the whole viewer; skip it.
            continue
    return index


def _papers_in_store() -> list[dict]:
    """Rows from the `papers` table; [] if the DB or table is absent."""
    if not Path(DB_PATH).exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT sha256, filename, page_count, doi FROM papers ORDER BY added_at"
        ).fetchall()
    except sqlite3.OperationalError:  # no `papers` table yet
        return []
    finally:
        conn.close()
    return [
        {"sha256": r[0], "filename": r[1], "page_count": r[2], "doi": r[3]}
        for r in rows
    ]


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    index = _pdf_index()
    items = []
    for p in _papers_in_store():
        sha = p["sha256"]
        label = html.escape(p["filename"] or sha[:12])
        if sha in index:
            items.append(
                f'<li><a href="/paper/{sha}">{label}</a> '
                f'<small>{p["page_count"]} pp · {sha[:12]}…</small></li>'
            )
        else:
            items.append(f"<li>{label} <small>(no PDF bytes on disk)</small></li>")
    body = "\n".join(items) or "<li>no papers in store</li>"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>palimpsest viewer</title></head><body>"
        "<h1>palimpsest — papers in store</h1>"
        f"<ul>{body}</ul></body></html>"
    )


@app.get("/paper/{sha}", response_class=HTMLResponse)
def paper(request: Request, sha: str):
    index = _pdf_index()
    if sha not in index:
        raise HTTPException(status_code=404, detail=f"no PDF for sha {sha}")
    meta = next((p for p in _papers_in_store() if p["sha256"] == sha), {})
    return templates.TemplateResponse(
        request,
        "viewer.html",
        {
            "sha": sha,
            "filename": meta.get("filename") or index[sha].name,
            "page_count": meta.get("page_count"),
        },
    )


@app.get("/paper/{sha}/pdf")
def paper_pdf(sha: str):
    path = _pdf_index().get(sha)
    if path is None:
        raise HTTPException(status_code=404, detail=f"no PDF for sha {sha}")
    return FileResponse(path, media_type="application/pdf")


# ----------------------------------------------------------------- data pane


@lru_cache(maxsize=1)
def _graph_store() -> RDFStore:
    """Disk-backed RDF store holding the extraction triples (T24).

    Opened once (RocksDB takes a directory lock; the viewer is read-mostly). An
    absent/empty `store/` opens as an empty store, so the data route returns []
    rather than 500. Tests monkeypatch this to inject an in-memory store.
    """
    return RDFStore(STORE_PATH)


@lru_cache(maxsize=1)
def _type_names() -> dict[str, str]:
    """Measurement `rdf:type` IRI -> human class name (e.g. 'Overpotential').

    `slot_path` in the JSON is this friendly name; EMMO-bound classes otherwise
    surface as opaque hash IRIs. Built by reading each generated Measurement
    subclass's `class_uri` and expanding the CURIE the same way `store.py` does.
    """
    out: dict[str, str] = {}
    for name, obj in inspect.getmembers(_schema, inspect.isclass):
        if obj is _schema.Measurement or not issubclass(obj, _schema.Measurement):
            continue
        if obj.__module__ != _schema.__name__:  # skip pydantic re-exports
            continue
        meta = getattr(obj, "linkml_meta", None)
        curie = meta.root.get("class_uri") if meta is not None and hasattr(meta, "root") else None
        if curie:
            out[_expand(curie)] = name
    return out


# One SELECT joining each measurement to its Evidence (provenance) for a given
# paper. value/unitLabel/sourceText/confidence are OPTIONAL — only written when
# present (store.py skips None); page/bbox/parserName are schema-required. The
# extraction model lives in the per-run named graph (store.py T-app), so it is
# joined via a GRAPH clause and is OPTIONAL (legacy/untagged data has none).
_DATA_QUERY = """\
PREFIX palim: <https://w3id.org/palimpsest/>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?m ?type ?value ?unit ?page ?bx0 ?by0 ?bx1 ?by1 ?parser ?src ?conf ?model WHERE {{
  ?m rdf:type ?type ;
     prov:hadPrimarySource ?ev .
  ?ev palim:paper <{paper}> ;
      palim:page ?page ;
      palim:bboxX0 ?bx0 ; palim:bboxY0 ?by0 ;
      palim:bboxX1 ?bx1 ; palim:bboxY1 ?by1 ;
      palim:parserName ?parser .
  OPTIONAL {{ ?m palim:value ?value }}
  OPTIONAL {{ ?m palim:unitLabel ?unit }}
  OPTIONAL {{ ?m palim:confidence ?conf }}
  OPTIONAL {{ ?ev palim:sourceText ?src }}
  OPTIONAL {{ GRAPH ?g {{ ?m palim:extractionModel ?model }} }}
}}
ORDER BY ?page ?m"""

# Per-paper (parser, model) cells + measurement counts — the source for the
# viewer's parser×model selector. model is OPTIONAL (legacy data → unbound).
_RUNS_QUERY = """\
PREFIX palim: <https://w3id.org/palimpsest/>
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?parser ?model (COUNT(DISTINCT ?m) AS ?n) WHERE {{
  ?m prov:hadPrimarySource ?ev .
  ?ev palim:paper <{paper}> ; palim:parserName ?parser .
  OPTIONAL {{ GRAPH ?g {{ ?m palim:extractionModel ?model }} }}
}}
GROUP BY ?parser ?model
ORDER BY ?parser ?model"""


def _num(v: str | None) -> float | str | None:
    """xsd:float/int literals come back as strings; coerce to float for JSON."""
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return v


def _int(v: str | None) -> int | None:
    """Page literal -> int; None if absent/unparseable so one bad row can't 500 the route."""
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _bbox(r: dict) -> list[float] | None:
    """The four coords as floats, or None if any is missing/non-numeric — the overlay
    skips a null bbox cleanly instead of doing math on a string (a NaN box)."""
    cs = [_num(r["bx0"]), _num(r["by0"]), _num(r["bx1"]), _num(r["by1"])]
    return cs if all(isinstance(c, float) for c in cs) else None


def _collect_triples(sha: str, parser: str | None = None, model: str | None = None) -> list[dict]:
    """Measurement rows for `sha`, each with provenance + confidence + model.

    `parser`/`model`, when given, post-filter the rows in Python (NOT interpolated
    into SPARQL — they come from the query string). [] for a non-hex sha.
    """
    if not _SHA_RE.match(sha):
        return []
    rows = _graph_store().sparql(_DATA_QUERY.format(paper=f"{PALIM}paper/{sha}"))
    names = _type_names()
    triples = [
        {
            "id": r["m"],
            "slot_path": names.get(r["type"], r["type"]),
            "value": _num(r["value"]),
            "unit": r["unit"],
            "page": _int(r["page"]),
            "bbox": _bbox(r),
            "parser_name": r["parser"],
            "source_text": r["src"],
            "confidence": _num(r["conf"]),
            "model": r["model"],
        }
        for r in rows
    ]
    if parser is not None:
        triples = [t for t in triples if t["parser_name"] == parser]
    if model is not None:
        triples = [t for t in triples if t["model"] == model]
    return triples


@app.get("/paper/{sha}/data")
def paper_data(sha: str, parser: str | None = None, model: str | None = None) -> dict:
    """Measurements for `sha` with value, unit, provenance, confidence, and model.

    Read-only over the RDF graph — no LLM, no spend. Optional `parser`/`model`
    query params filter to one matrix cell. Unknown/non-hex sha yields an empty
    `triples` list with 200 (not 404) so the data pane renders an empty state.
    """
    return {"sha": sha, "triples": _collect_triples(sha, parser, model)}


def _page_geometry(sha: str, parser: str) -> dict:
    """Per-page reference size + coordinate mode for placing a parser's bboxes.

    docling bboxes are PDF points (mode "points"); paddle bboxes are image pixels
    with a known reference page size in its cached output (mode "pixels"). mineru/
    dots cached outputs carry no page size (mode "none"), so the viewer can't place
    their boxes without a re-parse. Returns ``{"mode", "pages": {page_no: [w, h]}}``.
    """
    if parser not in ParserCache.PARSERS:
        return {"mode": "none", "pages": {}}
    path = ParserCache().get_output(sha, parser)
    if path is None or path.suffix != ".json":
        return {"mode": "none", "pages": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"mode": "none", "pages": {}}
    pages: dict[int, list[float]] = {}
    if parser == "docling":  # .pages is {page_no_str: {size: {width, height}}}, points
        for k, pg in (data.get("pages") or {}).items():
            try:
                size = pg.get("size", {})
                pages[int(k)] = [float(size["width"]), float(size["height"])]
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        return {"mode": "points", "pages": pages}
    if parser == "paddle":  # .pages[].res.{page_index, width, height}, pixels
        for pg in data.get("pages", []):
            res = pg.get("res", {}) if isinstance(pg, dict) else {}
            idx = res.get("page_index")
            if isinstance(idx, int) and "width" in res and "height" in res:
                pages[idx + 1] = [float(res["width"]), float(res["height"])]
        return {"mode": "pixels", "pages": pages}
    return {"mode": "none", "pages": {}}  # mineru/dots: no page size cached


@app.get("/paper/{sha}/pageinfo/{parser}")
def paper_pageinfo(sha: str, parser: str) -> dict:
    """Reference page sizes + coordinate mode for `parser`, so the viewer can place
    pixel-parser bboxes (docling=points, paddle=pixels, mineru/dots=none)."""
    if not _SHA_RE.match(sha):
        raise HTTPException(status_code=400, detail="non-hex sha")
    if parser not in ParserCache.PARSERS:
        raise HTTPException(status_code=400, detail=f"unknown parser: {parser}")
    return {"sha": sha, "parser": parser, **_page_geometry(sha, parser)}


@app.get("/paper/{sha}/runs")
def paper_runs(sha: str) -> dict:
    """Distinct (parser, model) cells + measurement counts for `sha`.

    The data source for the viewer's parser×model selector. `model` is null for
    legacy/untagged extractions. Read-only; empty for a non-hex sha.
    """
    if not _SHA_RE.match(sha):
        return {"sha": sha, "runs": []}
    rows = _graph_store().sparql(_RUNS_QUERY.format(paper=f"{PALIM}paper/{sha}"))
    runs = [{"parser": r["parser"], "model": r["model"], "count": int(r["n"])} for r in rows]
    return {"sha": sha, "runs": runs}


@app.get("/paper/{sha}/parse/{parser}")
def paper_parse(sha: str, parser: str):
    """Serve the cached RAW parse output (JSON/Markdown) for `sha`+`parser`.

    Read-only file serve from the parse-once cache (no parse, no GPU). 400 on a
    non-hex sha or unknown parser; 404 if that parser's output isn't cached.
    """
    if not _SHA_RE.match(sha):
        raise HTTPException(status_code=400, detail="non-hex sha")
    if parser not in ParserCache.PARSERS:
        raise HTTPException(status_code=400, detail=f"unknown parser: {parser}")
    path = ParserCache().get_output(sha, parser)
    if path is None:
        raise HTTPException(status_code=404, detail=f"no cached {parser} output for {sha[:12]}")
    media = "application/json" if path.suffix == ".json" else "text/plain; charset=utf-8"
    return FileResponse(path, media_type=media)


@app.get("/paper/{sha}/spans/{parser}")
def paper_spans(sha: str, parser: str) -> dict:
    """The parser's projected text spans (page + text) — the "Parser" funnel tab.

    Reads the parse-once cache and runs the SAME per-parser span adapter extraction
    consumes (`extract._load_spans`). Read-only: no LLM, no GPU, no spend. This is
    the granular "so many values" view that narrows into Schema then Gold. Chandra
    (no geometry) yields count 0. 400 non-hex/unknown parser; 404 if uncached.
    """
    if not _SHA_RE.match(sha):
        raise HTTPException(status_code=400, detail="non-hex sha")
    if parser not in ParserCache.PARSERS:
        raise HTTPException(status_code=400, detail=f"unknown parser: {parser}")
    path = ParserCache().get_output(sha, parser)
    if path is None:
        raise HTTPException(status_code=404, detail=f"no cached {parser} output for {sha[:12]}")
    try:  # a mis-shaped (but valid-JSON) cache file must degrade to empty, not 500 a read route
        spans = _load_spans(parser, path.read_text(encoding="utf-8"))
    except (AttributeError, TypeError, KeyError, ValueError):
        spans = []
    # bbox is the parser's NATIVE region (same coord space as /pageinfo) so the viewer
    # can highlight where the parser read each span — see how the parser carved the page.
    return {"sha": sha, "parser": parser, "count": len(spans),
            "spans": [{"page": p, "text": t, "bbox": list(b)} for p, t, b in spans]}


@lru_cache(maxsize=1)
def _gold_module():
    """Load `experiments/ab_extract.py` (GOLD + the benchmark matcher) by file path.

    ponytail: deliberate file-path import, NOT a package import — experiments/ has no
    __init__, and the engine must not duplicate the gold (ab_extract.py stays the
    single source of truth, so the viewer's match == the benchmark's). Returns None
    if the file is absent (installed package without the repo) so the Gold tab
    degrades to "no gold" instead of 500ing. (alt: extract GOLD to a shared JSON —
    rejected to avoid touching the live benchmark.)
    """
    path = Path("experiments/ab_extract.py")
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("_palim_gold", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # top-level is defs + load_dotenv(); main() is __main__-gated
    except Exception:
        return None
    return mod


@app.get("/paper/{sha}/gold")
def paper_gold(sha: str, parser: str | None = None, model: str | None = None) -> dict:
    """Extracted-vs-gold for one cell — the "Gold" funnel tab.

    Greedy-matches the cell's extracted (type, value) against the paper's gold using
    the benchmark's own `_matches` predicate (so the numbers equal ab_extract
    scoring). Reports each gold tuple's matched flag (✓/missed), each extracted
    value's matched flag (False ⇒ false positive / not-in-gold), and tp/fp/fn +
    recall/precision. `gold_total` 0 ⇒ no gold for this sha (tab says so).
    """
    mod = _gold_module()
    gold = (getattr(mod, "GOLD", {}) or {}).get(sha, []) if mod else []
    matches = getattr(mod, "_matches", None) if mod else None
    preds = [(t["slot_path"], t["value"]) for t in _collect_triples(sha, parser, model)]
    matched_gold = [False] * len(gold)
    pred_hit = [False] * len(preds)
    if matches is not None:
        for pi, (pt, pv) in enumerate(preds):  # same greedy order as ab_extract._score_preds
            for gi, (gt, gv) in enumerate(gold):
                if not matched_gold[gi] and matches(pt, pv, gt, gv):
                    matched_gold[gi] = pred_hit[pi] = True
                    break
    tp = sum(matched_gold)
    return {
        "sha": sha,
        "gold_total": len(gold),
        "tp": tp, "fn": len(gold) - tp, "fp": sum(1 for h in pred_hit if not h),
        "recall": tp / len(gold) if gold else 0.0,
        "precision": tp / len(preds) if preds else 0.0,
        "gold": [{"type": g[0], "value": g[1], "matched": matched_gold[i]}
                 for i, g in enumerate(gold)],
        "extracted": [{"type": p[0], "value": p[1], "matched": pred_hit[i]}
                      for i, p in enumerate(preds)],
    }


@app.get("/paper/{sha}/export")
def paper_export(sha: str, parser: str | None = None, model: str | None = None,
                 format: str = "json"):
    """Export the current (optionally parser/model-filtered) view as JSON or CSV."""
    triples = _collect_triples(sha, parser, model)
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["measurement", "slot", "value", "unit", "confidence",
                    "page", "bbox", "parser", "model", "source_text"])
        for t in triples:
            w.writerow([t["id"], t["slot_path"], t["value"], t["unit"], t["confidence"],
                        t["page"], json.dumps(t["bbox"]), t["parser_name"], t["model"],
                        t["source_text"]])
        return Response(
            content=buf.getvalue(), media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="palimpsest-{sha[:12]}.csv"'},
        )
    return {"sha": sha, "triples": triples}


# ------------------------------------------------------------- corrections (WS1)

# Corrections for a paper, oldest-first (the data pane keeps the newest per
# measurement). Lives in the corrections named graph, so a GRAPH clause is needed.
_CORRECTIONS_QUERY = """\
PREFIX palim: <https://w3id.org/palimpsest/>
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?c ?m ?author ?comment ?prior ?value ?unit ?flagged ?at WHERE {{
  GRAPH ?g {{
    ?c prov:wasRevisionOf ?m ;
       palim:paper <{paper}> ;
       palim:correctionAuthor ?author ;
       palim:correctionComment ?comment ;
       prov:generatedAtTime ?at .
    OPTIONAL {{ ?c palim:priorValue ?prior }}
    OPTIONAL {{ ?c palim:correctedValue ?value }}
    OPTIONAL {{ ?c palim:correctedUnit ?unit }}
    OPTIONAL {{ ?c palim:flaggedWrong ?flagged }}
  }}
}}
ORDER BY ?at"""


class CorrectionIn(BaseModel):
    measurement_iri: str
    comment: str
    new_value: float | None = None
    new_unit: str | None = None
    flagged_wrong: bool = False


@app.get("/paper/{sha}/corrections")
def paper_corrections(sha: str) -> dict:
    """Corrections recorded for `sha` (= labeled extractor errors), oldest-first JSON.

    Read-only over the corrections named graph; non-hex sha yields an empty list.
    """
    if not _SHA_RE.match(sha):
        return {"sha": sha, "corrections": []}
    rows = _graph_store().sparql(_CORRECTIONS_QUERY.format(paper=f"{PALIM}paper/{sha}"))
    corrections = [
        {
            "id": r["c"],
            "measurement_id": r["m"],
            "author": r["author"],
            "comment": r["comment"],
            "prior_value": _num(r["prior"]),
            "corrected_value": _num(r["value"]),
            "corrected_unit": r["unit"],
            "flagged_wrong": r["flagged"] == "true",
            "at": r["at"],
        }
        for r in rows
    ]
    return {"sha": sha, "corrections": corrections}


@app.post("/paper/{sha}/correct")
def post_correct(sha: str, body: CorrectionIn) -> dict:
    """Record a human correction to a measurement — the viewer's one write path.

    Appends a superseding correction via the shared primitive, reusing this
    process's already-open store (RocksDB is single-writer; a second handle would
    deadlock). 400 on a non-hex sha; 422 on a refused correction (empty / no
    Evidence anchor). The original triple is never touched.
    """
    if not _SHA_RE.match(sha):
        raise HTTPException(status_code=400, detail="non-hex sha")
    try:
        r = correct_measurement(
            _graph_store(),
            measurement_iri=body.measurement_iri,
            comment=body.comment,
            author="human",
            new_value=body.new_value,
            new_unit=body.new_unit,
            flagged_wrong=body.flagged_wrong,
        )
    except CorrectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "correction_iri": r.correction_iri,
        "prior_value": r.prior_value,
        "prior_unit": r.prior_unit,
        "commit": r.commit_sha,
    }
