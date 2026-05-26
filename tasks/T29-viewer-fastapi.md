# T29 — FastAPI viewer skeleton with PDF.js

## Why
Provenance viewer. Two-pane: PDF on left, extracted data on right. Hovering a value highlights its bbox.

## Input state
- T25 merged. Pipeline produces graph with provenance.

## Output state
- File `src/palimpsest/viewer/app.py` exports `app: FastAPI` with routes:
  - `GET /` → renders home (list of papers in store).
  - `GET /paper/{sha}` → renders viewer template (PDF left, data right placeholder).
  - `GET /paper/{sha}/pdf` → streams the PDF bytes.
  - `GET /health` → returns `{"ok": True}`.
- File `src/palimpsest/viewer/templates/viewer.html` is a Jinja2 template with:
  - Two-pane CSS grid layout (PDF | data).
  - PDF.js loaded from `static/pdfjs/` (vendored).
  - HTMX loaded from CDN (`https://unpkg.com/htmx.org@latest`).
  - Empty `<div id="data-pane">` for T30 to populate.
- File `src/palimpsest/viewer/static/pdfjs/` — vendored PDF.js (download from https://github.com/mozilla/pdf.js/releases, latest stable; copy `pdf.min.mjs`, `pdf.worker.min.mjs`, viewer assets).
- File `pixi.toml` adds `viewer = "uvicorn palimpsest.viewer.app:app --reload --port 8765"`.

## Verification
```bash
pixi run viewer
# In another terminal:
curl http://localhost:8765/health   # → {"ok":true}
# Open http://localhost:8765/paper/<sha-from-T25> in a browser; PDF should render.
```

## Will touch
- `src/palimpsest/viewer/app.py` (full)
- `src/palimpsest/viewer/templates/viewer.html` (new)
- `src/palimpsest/viewer/static/pdfjs/...` (vendored, ~10 files)
- `pixi.toml` (edit: add viewer task)

## Will NOT touch
- agent.py, tui/.

## Out of scope
- Data endpoint → T30.
- Hover highlight → T31.

## Notes / references
- FastAPI + Jinja2: https://fastapi.tiangolo.com/advanced/templates/
- Vendoring PDF.js avoids a CDN dependency. Use the `mozilla.github.io/pdf.js` ESM build.
- No build step. No bundler. Pure HTML + ESM imports.
