// T31 — hover a data row, highlight its source bbox over the PDF.
//
// Coords are PARSER-NATIVE (see T31 card), not uniformly PDF points:
//   docling                = PDF user space, points, bottom-left origin
//                            -> viewport.convertToViewportRectangle handles the
//                               scale and the Y-flip to canvas top-left.
//   mineru / dots / paddle = image pixels, top-left origin
//                            -> no Y-flip, scale by canvas/reference-page ratio.
// The MVP is backed on docling; the pixel branch is the seam for the deferred
// per-parser toggle. It needs the parser's reference page size to scale into
// canvas space, which isn't carried to the DOM yet, so it skips rather than draw
// a misplaced box on the docling-backed viewer.

let overlayDivs = [];

function clearHighlights() {
  for (const d of overlayDivs) d.remove();
  overlayDivs = [];
}

function highlightBox(rowEl) {
  clearHighlights();

  const page = Number(rowEl.dataset.page);
  const bbox = JSON.parse(rowEl.dataset.bbox || "null");
  const parser = rowEl.dataset.parser || "docling";
  const entry = (window.palimPages || {})[page];
  if (!entry || !Array.isArray(bbox) || bbox.length !== 4) return;

  const { viewport, wrap } = entry;
  let left, top, width, height;

  if (parser === "docling") {
    // [x0,y0,x1,y1] in PDF points -> viewport (canvas) pixels, top-left origin.
    // The returned corners may come back in either order, so normalize.
    const [vx0, vy0, vx1, vy1] = viewport.convertToViewportRectangle(bbox);
    left = Math.min(vx0, vx1);
    top = Math.min(vy0, vy1);
    width = Math.abs(vx1 - vx0);
    height = Math.abs(vy1 - vy0);
  } else {
    // Pixel/top-left parsers need their reference page size to scale correctly;
    // deferred per-parser toggle ships it. Skip over guessing.
    console.warn(`bbox highlight for "${parser}" needs a reference page size (deferred); skipping`);
    return;
  }

  const div = document.createElement("div");
  div.className = "bbox-overlay";
  div.style.left = left + "px";
  div.style.top = top + "px";
  div.style.width = width + "px";
  div.style.height = height + "px";
  wrap.appendChild(div);
  overlayDivs.push(div);

  wrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
