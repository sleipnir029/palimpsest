// Hover/click a data card → highlight its source bbox over the PDF.
//
// The extraction tightening pass relocates each box to the exact value text in PDF
// points (bottom-left origin), so a refined box fits the page's own point box no
// matter which parser cited it. We detect that by bounds and use the points path
// (viewport.convertToViewportRectangle handles scale + Y-flip via PDF.js geometry —
// no reference size needed). That single path is what lets mineru/dots boxes draw.
//
// Anything NOT in the point box is parser-native pixels (un-tightened): we fall back
// to the per-parser /pageinfo mode — paddle="pixels" (scaled by its refw/refh),
// mineru/dots="none" → return false so the caller says so honestly, never a
// misplaced box.
//
// highlightBox(el, scroll=false) -> bool (true if a box was drawn). Scroll only on an
// explicit click (scroll=true); hovering must NOT yank the PDF around.

let overlayDivs = [];

function clearHighlights() {
  for (const d of overlayDivs) d.remove();
  overlayDivs = [];
}

function highlightBox(rowEl, scroll = false) {
  clearHighlights();

  const page = Number(rowEl.dataset.page);
  const bbox = JSON.parse(rowEl.dataset.bbox || "null");
  const parser = rowEl.dataset.parser || "docling";
  const entry = (window.palimPages || {})[page];
  if (!entry || !Array.isArray(bbox) || bbox.length !== 4) return false;

  const { viewport, wrap } = entry;
  // A tightened box is PDF points (bottom-left) → it fits the page's point box for
  // any parser. Detect by bounds and prefer the points path; else fall back to the
  // per-parser /pageinfo mode (paddle="pixels", mineru/dots="none").
  const vb = viewport.viewBox;  // [x0,y0,x1,y1] page box in PDF points
  const inPoints = bbox[0] >= vb[0] - 1 && bbox[1] >= vb[1] - 1 &&
                   bbox[2] <= vb[2] + 1 && bbox[3] <= vb[3] + 1;
  const mode = inPoints ? "points"
             : (rowEl.dataset.mode || (parser === "docling" ? "points" : "none"));
  let left, top, width, height;

  if (mode === "points") {
    // [x0,y0,x1,y1] in PDF points -> viewport (canvas) pixels (handles scale + Y-flip).
    const [vx0, vy0, vx1, vy1] = viewport.convertToViewportRectangle(bbox);
    left = Math.min(vx0, vx1); top = Math.min(vy0, vy1);
    width = Math.abs(vx1 - vx0); height = Math.abs(vy1 - vy0);
  } else if (mode === "pixels" && rowEl.dataset.refw && rowEl.dataset.refh) {
    // image pixels, top-left origin (no flip) -> scale by canvas/reference-page ratio.
    const sx = viewport.width / parseFloat(rowEl.dataset.refw);
    const sy = viewport.height / parseFloat(rowEl.dataset.refh);
    const [x0, y0, x1, y1] = bbox;
    left = Math.min(x0, x1) * sx; top = Math.min(y0, y1) * sy;
    width = Math.abs(x1 - x0) * sx; height = Math.abs(y1 - y0) * sy;
  } else {
    return false;  // no reference size → don't guess at a box
  }

  const div = document.createElement("div");
  div.className = "bbox-overlay";
  Object.assign(div.style, {
    left: left + "px", top: top + "px", width: width + "px", height: height + "px",
  });
  wrap.appendChild(div);
  overlayDivs.push(div);

  if (scroll) wrap.scrollIntoView({ behavior: "smooth", block: "center" });
  return true;
}
