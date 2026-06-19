# T42 — Thesis chapter: parser comparison

**Status:** planned (writing) · **Group:** thesis · **Priority:** medium · **Depends:** T36–T41

> **Updated 2026-06-19** — corrections + framing:
> - Parser set is **{docling, MinerU 2.5, dots.ocr, PaddleOCR}** — **Chandra excluded**
>   (no geometry + timeouts, T34); report it separately as "excluded," not as a score.
> - The "single LLM for downstream" limitation this card lists is now *partly answered*
>   by the sibling study **T72** (LLM breadth matrix) — cross-reference it in Discussion
>   instead of only listing it as a limitation.
> - Lead the chapter with the **downstream-extraction-accuracy** result (T39), the
>   thesis's principal claim; transcription/table/bbox metrics are supporting.
> - See `report/supervisor-answers-2026-06-19.md` §1 for the shared metric + baseline design.

## Why
The headline parser study (contribution #2): head-to-head comparison of docling,
MinerU 2.5, dots.ocr, and PaddleOCR on OER catalyst papers, evaluated on transcription
fidelity AND downstream extraction accuracy.

## Input state
- T36–T39 (the 4 metrics) and T41 (plots) merged.

## Output state
- File `thesis/02_parser_comparison.md` containing:
  - Section: Motivation (why compare parsers for scientific PDF extraction).
  - Section: Methodology (corpus, ground truth, metrics).
  - Section: Results — 4 subsections, one per metric, each with a table and a figure reference.
  - Section: Discussion — which parser wins on which metric, why, trade-offs (speed, cost, VRAM).
  - Section: Recommendation — which parser to use for which scenario.
  - Section: Limitations — small sample, single domain, single LLM for downstream.
- Word count target: 2500–4000 words.
- All figures referenced are in `thesis/figures/`.
- All tables generated programmatically from `experiments/*.csv` (cite the CSV).

## Verification
```bash
test -f thesis/02_parser_comparison.md
wc -w thesis/02_parser_comparison.md   # expect 2500–4000
grep -c "figures/" thesis/02_parser_comparison.md  # expect ≥4
```

## Will touch
- `thesis/02_parser_comparison.md` (new)

## Will NOT touch
- experiments/*, notebooks/*, figures/*.

## Out of scope
- Ontology gap chapter → T43.
- Methodology/reflection chapter → T44.

## Notes / references
- Write in scientific style: passive voice acceptable, results-then-discussion, hedged claims with citations.
- This is the chapter your supervisor will read first. Make it rigorous.
- 4 hours.
