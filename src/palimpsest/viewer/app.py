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

import html
import inspect
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from schema.generated import pydantic as _schema  # PEP 420 namespace pkg

from ..corrections import CorrectionError, correct_measurement
from ..cost import canonical_db
from ..store import PALIM, RDFStore, _expand
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
# paper. value/unitLabel/sourceText are OPTIONAL — only written when present
# (store.py skips None); page/bbox/parserName are schema-required.
_DATA_QUERY = """\
PREFIX palim: <https://w3id.org/palimpsest/>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?m ?type ?value ?unit ?page ?bx0 ?by0 ?bx1 ?by1 ?parser ?src WHERE {{
  ?m rdf:type ?type ;
     prov:hadPrimarySource ?ev .
  ?ev palim:paper <{paper}> ;
      palim:page ?page ;
      palim:bboxX0 ?bx0 ; palim:bboxY0 ?by0 ;
      palim:bboxX1 ?bx1 ; palim:bboxY1 ?by1 ;
      palim:parserName ?parser .
  OPTIONAL {{ ?m palim:value ?value }}
  OPTIONAL {{ ?m palim:unitLabel ?unit }}
  OPTIONAL {{ ?ev palim:sourceText ?src }}
}}
ORDER BY ?page ?m"""


def _num(v: str | None) -> float | str | None:
    """xsd:float/int literals come back as strings; coerce to float for JSON."""
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return v


@app.get("/paper/{sha}/data")
def paper_data(sha: str) -> dict:
    """All measurements for `sha` with value, unit, and provenance, as JSON.

    Read-only over the RDF graph — no LLM, no spend. Unknown sha (or a non-hex
    sha, which must never reach the SPARQL string) yields an empty `triples`
    list with 200 — not a 404 like the sibling /paper routes — so the HTMX data
    pane renders an empty state cleanly.
    """
    if not _SHA_RE.match(sha):
        return {"sha": sha, "triples": []}
    rows = _graph_store().sparql(_DATA_QUERY.format(paper=f"{PALIM}paper/{sha}"))
    names = _type_names()
    triples = [
        {
            "id": r["m"],
            "slot_path": names.get(r["type"], r["type"]),
            "value": _num(r["value"]),
            "unit": r["unit"],
            "page": int(r["page"]) if r["page"] is not None else None,
            "bbox": [_num(r["bx0"]), _num(r["by0"]), _num(r["bx1"]), _num(r["by1"])],
            "parser_name": r["parser"],
            "source_text": r["src"],
        }
        for r in rows
    ]
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
