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
- PDF.js coordinate system: PDF user space is bottom-left origin, viewport is top-left origin. `convertToViewportRectangle` handles the flip — **but only for bboxes already in PDF user space (points)**. See the forward-compat note below: stored bboxes are *parser-native*, so this is correct for **docling** (points, bottom-left) and WRONG for mineru/dots/paddle (pixels, top-left). Build the MVP on docling.
- Bbox needs to be page-relative AND scale-aware. If PDF.js is rendering at scale 1.5, your overlay div positions need to multiply by 1.5.
- Reference: Yury Delendik's PDF.js highlighting gist (search "pdf.js highlight rectangle gist" — there's a canonical example).
- This task is the most visually rewarding. Take the time to get it right.

## Forward-compat & deferred multi-parser toggle (added 2026-06-16)
A live demo run (MinerU) showed block-level bboxes — 5 distinct boxes back 18
values, 8 sharing one — so highlights are coarse and collide. User decided to
build the single-parser viewer first, then add a per-parser toggle on top. Build
T31 so the toggle is *additive*, honoring these constraints:

1. **Coords are parser-native, not uniformly PDF points.** docling = points,
   bottom-left (matches `convertToViewportRectangle`); mineru/dots/paddle =
   pixels, top-left (need their reference page size + no PDF-space flip). Write
   `highlightBox(...)` to take the parser (or a coord-space tag) and branch the
   transform, even though the MVP wires one parser.
2. **Back the MVP on docling, not the mineru default.** Finest spans (~656 vs 144
   → tight, non-colliding boxes) AND simplest coords. T51 span-projection feeds
   docling's 19 MB output to the LLM at ~25K tok, so `extract(sha, "docling")`
   works. Populate `store/` via `demo <pdf>` at `parser="docling"`.
3. **Carry `parser_name` to the DOM** (`data-parser="..."` on each row) — `/data`
   already returns it; the future per-parser branch/selector then drops in.
4. **Don't bake single-parser assumptions into `/data`.** Future `?parser=`
   filter; default (no param) stays "all triples for sha".

**Deferred toggle design (build AFTER T31 verified):** semantics = "each parser's
own extraction" (value list varies per parser). Storage is free — `store.py`
stamps Evidence with `parser_name`, so loop `run_paper(sha, parser=p)` over the 4
geometry parsers (~€0.016/paper, sample cached → no GPU), add `?parser=` to
`/data` + a `/paper/{sha}/parsers` list, and a selector in `viewer.html`. chandra
excluded (no geometry → no bbox → can't insert per provenance non-negotiable).
