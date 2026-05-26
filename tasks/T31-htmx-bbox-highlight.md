# T31 — HTMX bbox highlight on hover

## Why
The provenance viewer's signature feature: hover a value in the right pane, see the source bbox highlighted in the PDF.

## Input state
- T30 merged. /data endpoint returns triples.

## Output state
- `viewer/templates/viewer.html` updated:
  - On page load, fetch `/paper/{{sha}}/data` (via HTMX `hx-get` on the data pane).
  - Render each triple as a row: `<div class="value" data-page="..." data-bbox="..." onmouseover="highlightBox(...)">value unit</div>`.
- File `src/palimpsest/viewer/static/pdf-overlay.js` (new, ~50 LOC):
  - `let overlayDivs = []`
  - `function highlightBox(page, x0, y0, x1, y1)`:
    1. Clear existing overlays.
    2. Find the PDF.js canvas for the page (or scroll to it).
    3. Get the page's viewport (`page.getViewport({ scale: ... })`).
    4. Convert PDF coords to viewport coords via `viewport.convertToViewportRectangle([x0,y0,x1,y1])`.
    5. Create a `<div>` positioned absolutely over the canvas with semi-transparent yellow background.
    6. Append to overlay layer.
  - `function clearHighlights()`.
- File `tests/test_viewer_e2e.py` (optional, marked `@pytest.mark.slow`): use Playwright or httpx to fetch the page, parse for `data-bbox` attributes, assert at least one row exists.

## Verification
- Manual: `pixi run viewer`, open browser, hover values, see bboxes highlight correctly.
- Automated:
```bash
pixi run pytest tests/test_viewer_e2e.py -v -m slow
```

## Will touch
- `src/palimpsest/viewer/templates/viewer.html` (edit)
- `src/palimpsest/viewer/static/pdf-overlay.js` (new)
- `tests/test_viewer_e2e.py` (optional new)

## Will NOT touch
- /data endpoint (T30 stable).
- Vendored PDF.js (don't modify upstream code).

## Out of scope
- Click-to-jump (just hover).
- Editing values in the right pane.
- Multi-page selection.

## Notes / references
- PDF.js coordinate system: PDF user space is bottom-left origin, viewport is top-left origin. `convertToViewportRectangle` handles the flip.
- Bbox needs to be page-relative AND scale-aware. If PDF.js is rendering at scale 1.5, your overlay div positions need to multiply by 1.5.
- Reference: Yury Delendik's PDF.js highlighting gist (search "pdf.js highlight rectangle gist" — there's a canonical example).
- This task is the most visually rewarding. Take the time to get it right.
