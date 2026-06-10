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
