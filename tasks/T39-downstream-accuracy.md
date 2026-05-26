# T39 — Downstream extraction accuracy by parser

## Why
The most thesis-relevant metric: given each parser's output, how well does Sonnet 4.5 extract correct values?

## Input state
- T22 (extract) + T35 (ground truth) merged.

## Output state
- File `experiments/downstream_accuracy.py`:
  - For each of the 5 ground-truth papers:
    - For each parser (docling, mineru, olmocr, chandra):
      - Call `extract(paper_sha, parser_name)` to get Pydantic instances.
      - For each ground-truth label, find the matching extraction (by slot name).
      - Score: exact value match, within-tolerance match (10% relative), or miss.
  - Aggregate to per-parser metrics: % exact, % within-tolerance, % miss.
- File `experiments/downstream_accuracy.csv`.

## Verification
```bash
pixi run python experiments/downstream_accuracy.py
test -f experiments/downstream_accuracy.csv
```

## Will touch
- `experiments/downstream_accuracy.py` (new)
- `experiments/downstream_accuracy.csv` (generated)

## Will NOT touch
- extract.py (T22 stable).

## Out of scope
- Per-slot deep dive — keep this at the aggregate level.

## Notes / references
- This experiment will cost LLM money: 5 papers × 4 parsers × ~$0.30 = ~$6. Budget for it.
- Cache aggressively: the system prompt + schema + skill is identical across all 20 extractions; only the parser output changes. Cache should give 90%+ hit rate.
- This is THE metric your thesis will lead with. Make sure the numbers are reproducible — log seeds, model versions, prompt hashes.
