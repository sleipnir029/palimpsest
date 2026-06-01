# Palimpsest report — LaTeX edition

RWTH-styled LaTeX build of `../palimpsest-report.md`, adapted from the reference
project in `../reference project files/`. Designed to compile **fast and locally** —
no Overleaf, no per-compile-heavy dependencies (`minted`, `svg`, `biblatex` are
deliberately not used).

## Files
- `main.tex` — the report.
- `template.cls` — RWTH document class (title page, TOC, logo header/footer, code box).
- `logos/` — RWTH logo PNGs.
- figures are reused from `../figures/` via `\graphicspath`.
- `.vscode/settings.json` — LaTeX Workshop build recipe (pdflatex ×3, no latexmk/biber).

## Build in VS Code (recommended)
1. The **LaTeX Workshop** extension is installed.
2. **File → Open Folder…** and open **this `latex/` folder** (not the repo root), so
   `.vscode/settings.json` applies.
3. Open `main.tex`. Build with the ▶ (TeX badge → *Build LaTeX project*) or `⌘+Option+B`.
   Preview the PDF with the magnifier icon / `⌘+Option+V` (SyncTeX: ⌘-click jumps between
   source and PDF).

## Build from the terminal
```
cd report/latex
pdflatex main.tex && pdflatex main.tex && pdflatex main.tex
```
Three passes are needed for the table of contents, the long risks table (`longtable`),
and cross-references to settle. Output: `main.pdf`.

## Other free options
- **TeXShop** (bundled with the MacTeX/BasicTeX install): open `main.tex`, set the engine
  to *pdfLaTeX*, typeset 2–3 times.
- Any editor over the terminal command above.

## Regenerating the figures
The five figures live in `../figures/` as PNGs (committed). To regenerate from their
Mermaid sources, see the recipe in the `Figure 2 source` comment inside
`../palimpsest-report.md` (mermaid-cli with `htmlLabels` disabled).

## Notes
- Built on **BasicTeX 2026**; the following packages were added once with
  `sudo tlmgr install`: `tcolorbox tikzpagenodes siunitx enumitem ifoddpage pdfcol
  varwidth pgfopts xstring tikzfill listingsutf8`.
- Set `\enseignant{[matriculation no.]}` in `main.tex` to your matriculation number.
