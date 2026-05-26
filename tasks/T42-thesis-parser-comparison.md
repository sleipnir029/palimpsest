# T42 — Thesis chapter: parser comparison

## Why
The headline contribution: head-to-head comparison of docling, MinerU 2.5, olmOCR 2, Chandra 2 on OER catalyst papers.

## Input state
- T36–T39 (all 4 metrics) and T41 (plots) merged.

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
