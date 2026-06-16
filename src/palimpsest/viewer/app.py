"""FastAPI provenance viewer (T29 skeleton).

Two-pane page: PDF on the left (rendered by vendored PDF.js), extracted data on
the right (empty placeholder — T30 populates it, T31 adds bbox hover highlight).

PDF location is content-addressed: the `papers` table stores an unreliable
`filename` (fixture rows say 'sample.pdf'), so we resolve a sha256 -> path index
by hashing every `papers/*.pdf` with T07's `read_paper`. The bytes served for
`{sha}` therefore hash to exactly `{sha}` — provenance holds by construction.
"""

from __future__ import annotations

import html
import sqlite3
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..tools.read_paper import read_paper

_BASE = Path(__file__).parent
PAPERS_DIR = Path("papers")
DB_PATH = "palimpsest.db"

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
