# T49 — bbox from parser geometry + unit validation (C3+C2)

## Why
Provenance is currently enforced *present* but not *correct*. Bounding boxes are LLM-transcribed
from the parser's text dump and never cross-checked against parser-native geometry; Chandra emits
markdown with **no** geometry, so those bboxes are fabricated or null. Units are written as bare
strings with no validation. This matters most for the thesis: **T38 (bbox-precision metric) is
meaningless if bbox comes from the LLM** — it would measure LLM transcription, not parser
localization, inverting what the metric intends to measure.

## Input state
- T22 `tools/extract.py` injects the LLM-emitted bbox into `Evidence`.
- Parser outputs carry native geometry: docling / MinerU / dots / paddle JSON have per-span bboxes;
  Chandra markdown does not.
- `normalize.py` declares canonical units per metric but only injects them as prompt text.

## Output state
- `tools/extract.py` (or a new helper): after the LLM returns a snippet/quote + page, **resolve the
  bbox by matching the snippet against the parser's native geometry** and replace the LLM bbox with
  the parser-native one. Record a `bbox_source ∈ {parser, none}` on the Evidence/provenance.
- Chandra (no geometry): set bbox null + `bbox_source="none"`; **do not fabricate**. Decide and
  state whether Chandra is excluded from the bbox-precision metric (no silent caps — log the
  decision in the card/T38).
- **Unit validation:** in `normalize.py` or `extract.py`, reject/flag any `unit_label` that does
  not match the slot's canonical unit; route mismatches to the `errors` list, not into the graph
  (closes C2).
- `tests/test_extract.py`: a parser-native bbox is recovered for a known snippet; a wrong unit is
  rejected; a Chandra extraction yields `bbox_source="none"` without crashing.

## Verification
```bash
pixi run pytest tests/test_extract.py -v   # new bbox-resolution + unit-validation cases
```
The verification command MUST exit 0.

## Will touch
- `src/palimpsest/tools/extract.py` (edit)
- `src/palimpsest/normalize.py` (edit)
- `tests/test_extract.py` (edit)

## Will NOT touch
- `store.py` (consumes the corrected Evidence unchanged)
- `schema/palimpsest.yaml` — unless a `bbox_source` slot is needed; if so, add it via the schema,
  regenerate, and note it (do not add it ad-hoc in code).

## Out of scope
- The viewer's bbox-highlight endpoint (T31) consumes the corrected bbox later.
- A learned text→geometry aligner; start with exact/fuzzy snippet matching against parser spans.

## Notes / references
- This is the methodology fix from the 2026-06-10 review (C3+C2). Be explicit in T38/T42 about what
  bbox precision does and does not measure, and how Chandra is handled.
- Snippet matching: normalize whitespace/casing; match the LLM's `source_text` against the parser's
  span text, take the union bbox of matched spans.

## Implemented — Option B (minimal), 2026-06-12

User chose **Option B** over the card's implied Option A after the null-bbox dependency was
traced. The card's "Output state" assumed a `bbox_source ∈ {parser, none}` slot + nullable
bbox, which would have forced relaxing the schema's `required: true` on `bbox_x0..y1`
(T18a F4), regenerating `schema/generated/*`, guarding `store.py`, and fixing
`test_schema_gen.py`/`test_store.py` — ~8 files, and a relaxation of the bbox provenance
non-negotiable. **B keeps the schema and store.py untouched** and instead routes any
measurement whose bbox cannot be resolved (Chandra = no geometry; or a quote matching no
parser span) to `errors`. No `bbox_source` slot is stored — it would be the constant
`"parser"` for every valid item.

**Deviations from the card's literal Output/Verification, all accepted by the user:**
- No `bbox_source` slot; not recorded on Evidence/provenance.
- A Chandra extraction does NOT yield a valid instance with `bbox_source="none"` — it routes
  to `errors` "without crashing the batch" (the test was rewritten to that B-variant). Chandra
  (and any no-match measurement) is therefore excluded from the **graph entirely**, not just
  from the T38 metric. Logged here + in T38 (no silent cap).
- bboxes are stored in **native per-parser coordinates** (no normalization); the
  docling-BOTTOMLEFT-vs-others-TOPLEFT split and the Chandra exclusion are documented in
  `tasks/T38-metric-bbox-precision.md` for the metric to handle.

**Invariant gained:** every bbox in the graph is parser-native by construction — T38 measures
parser localization, not LLM transcription (the methodology fix C3).

**C2 unit validation — refined during live verification (user chose "Both").** Initial design
used exact-string `==` against `canonical_unit`. The first live run exposed that this rejects
*correct* units in paper-faithful spelling (LLM emits `s⁻¹` for canonical `1/s`, `A g⁻¹_Ir`
for `A/g`). Fix: `normalize.units_match()` reduces both units to a signed-token signature
(unicode/LaTeX superscripts → exponents, `/` and `⁻¹` → denominator, strip spaces + `_Ir`
qualifiers, `dec`≡`decade`), so `s⁻¹`≡`1/s` passes while `V`≢`mV` (a real 1000× error) still
fails. Plus the normalization prompt now shows ASCII-spelling examples. Mismatches route to
`errors` (closes C2).

**Matcher — whitespace-insensitive.** `_norm` removes ALL whitespace (not just collapses):
parsers pad inline equations with spaces the LLM's continuous quote lacks (mineru
`Ir- Co_{3}O_{4}` vs quote `Ir-Co_{3}O_{4}`). A `_MIN_SPAN_MATCH_CHARS` guard prevents
trivially short spans (docling's single-char `h`) from polluting the union bbox; `page` is
parsed tolerantly (`int("3")`).

**Files touched:** `src/palimpsest/tools/extract.py`, `src/palimpsest/normalize.py`,
`tests/test_extract.py` (card's 3) + `tests/test_normalize.py` (unit tests for the new
`units_match`/`canonical_unit` — justified by the new function). Doc-only: this card,
`tasks/T38-metric-bbox-precision.md`, `PROGRESS.md`.

**Verification.** Offline: `pixi run pytest tests/test_extract.py -v` → 14 passed / 1 live
skipped; full offline suite → **113 passed / 8 skipped, 0 failures** (0 regressions). All 5
parser adapters smoke-tested against the real `cache/3432…/` outputs (mineru 144, dots 148,
paddle 163, docling 656 spans over pages 1–12; chandra 0 = no geometry). **Live** (real cached
paper, user-authorized ~€0.30/run): final run **14 valid / 0 errors** — every measurement got
a parser-native bbox from its real quote, and all units (mV, A/g, 1/s, mV/decade) validated.
**Scope of live verification:** the live test globs `mineru.json`, so the full
quote→match→bbox path is live-verified for **mineru only**; the docling/dots/paddle adapters
are span-level smoke-tested (correct span extraction against real `cache/3432…/` outputs) but
not yet exercised end-to-end through the matcher. Chandra is intentionally no-geometry.
The matcher prefers the tightest single span that contains the quote and only unions when the
quote is split across spans (avoids inflating the bbox with unrelated same-page fragments —
matters most for fine-grained docling).

**Per-parser pipeline verification (closed in T50, 2026-06-13).** The docling/dots/paddle
adapters are now exercised end-to-end through `_load_spans` → `_resolve_bbox` by offline
deterministic tests (`tests/test_extract.py::test_per_parser_bbox_pipeline`) with synthetic
fixtures in each parser's real format — confirming each adapter feeds the matcher and resolves the
correct bbox. This is the only feasible check for docling (4.86M-token output) and paddle (217K),
which cannot be fed to extraction whole; that extraction-input size limit is a separate scaling
gap (chunking parser output is a future task, unrelated to the bbox matcher).
The iteration that got there: run 1 = 0 valid (units too strict) → run 2 = 8 valid/5 err
(units fixed, TafelSlope inline-equation spacing missed) → final = 14/0 (whitespace-insensitive
matcher). NOTE: the live verification runs drained the palimpsest Anthropic account's credit
balance — top up before the next live run; offline suite is unaffected.
