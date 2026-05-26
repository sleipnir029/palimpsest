# T34 — Parse full 25-paper corpus

## Why
Get all 25 OER catalyst papers parsed and cached. After this, all extraction work is offline (zero GPU cost).

## Input state
- T17 (cache verification) merged.
- `papers/` contains ≥25 PDFs (Rahat sourced them).

## Output state
- All 25 papers have 4 cached parser outputs each (100 rows in parser_runs).
- Total GPU spend recorded in cost ledger. Target: < €5.
- File `experiments/corpus_manifest.csv` listing each paper: sha256, filename, DOI, n_pages.

## Verification
```bash
pixi run python -c "
from palimpsest.cache import ParserCache
c = ParserCache()
shas = c.list_all_papers()
print(f'papers: {len(shas)}')
incomplete = [s for s in shas if not c.has_all_parsers(s)]
print(f'incomplete: {len(incomplete)}')
assert len(incomplete) == 0, f'missing: {incomplete}'
"
pixi run python -c "
from palimpsest.cost import CostMeter
m = CostMeter()
gpu = [e for e in m.list_ledger() if e['kind']=='gpu']
total = sum(e['amount_eur'] for e in gpu)
print(f'GPU spend: €{total:.2f} across {len(gpu)} entries')
assert total < 5, 'GPU spend exceeded €5'
"
```

## Will touch
- `experiments/corpus_manifest.csv` (new)
- Maybe `src/palimpsest/cache.py` (add `list_all_papers()` if missing — small edit).

## Will NOT touch
- src/palimpsest/parsers/* (T16 stable).

## Out of scope
- Extracting from the parsed outputs → T39 (extraction is part of the parser comparison experiment).
- Ground truth → T35.

## Notes / references
- This is mostly a wait task. Spin a pod, run `parse_with_cache(all_25_pdfs)`, drink coffee.
- If a specific paper fails on one parser, log it and continue. Some parsers will fail on weird PDFs; that's data.
- ~1 hour pod time. ~€0.50 at community cloud rates.
