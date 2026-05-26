# T16 — run_all_parsers in one GPU session

## Why
The whole point of the parse-once design: one pod startup, four parsers per paper, all caches written.

## Input state
- T14 (gpu_provider) + T15 (cache) merged.

## Output state
- File `src/palimpsest/parsers/runner.py` exports:
  - `def parse_with_cache(pdf_paths: list[Path], cost_meter, cache: ParserCache) -> dict[str, dict[str, Path]]`:
    1. For each PDF, compute sha256.
    2. Call `cache.list_unseen(pdfs)`. If all cached, return mapping from cache without starting pod.
    3. Otherwise, `with RunPodSession(cost_meter) as gpu:`
       - For each unseen `(pdf, sha)`:
         - `gpu.scp_up(pdf, f"/workspace/in/{pdf.name}")`
         - For each parser in `["docling", "mineru", "olmocr", "chandra"]`:
           - `gpu.ssh(f"<parser-specific command> in/{pdf.name} > out/{sha}_{parser}.json")`
           - `gpu.scp_down(f"/workspace/out/{sha}_{parser}.json", cache_dir / sha / f"{parser}.json")`
           - `cache.insert_parser_run(sha, parser, version, output_path, seconds, cost, run_id)`
       - `cache.add_paper(sha, filename, page_count)`
    4. Return mapping `{sha: {parser_name: Path}}`.
- File `src/palimpsest/parsers/commands.py` — module-level dict `PARSER_COMMANDS` mapping parser name to a function that returns the shell command string for that parser. Easier to test and easier to update when parser CLIs change.
- File `tests/test_runner.py` with mocked gpu_provider covers happy path and "all cached" short-circuit.

## Verification
```bash
pixi run pytest tests/test_runner.py -v
# Live, run once:
pixi run python -c "
from palimpsest.parsers.runner import parse_with_cache
from palimpsest.cache import ParserCache
from palimpsest.cost import CostMeter
from pathlib import Path
result = parse_with_cache([Path('tests/fixtures/sample.pdf')], CostMeter(), ParserCache())
sha = next(iter(result))
assert set(result[sha].keys()) == {'docling','mineru','olmocr','chandra'}
print('4 parsers cached for', sha[:12])
"
```
Mocked tests pass. Live invocation produces 4 cached outputs in `cache/<sha>/`.

## Will touch
- `src/palimpsest/parsers/runner.py` (new)
- `src/palimpsest/parsers/commands.py` (new)
- `src/palimpsest/parsers/__init__.py` (edit: exports)
- `tests/test_runner.py` (new)

## Will NOT touch
- gpu_provider.py (T14 stable).
- cache.py (T15 stable).

## Out of scope
- Cache hit verification → T17.
- Schema-aware extraction from parser output → T22.

## Notes / references
- The exact CLI commands for each parser need to be verified against the running Docker image (T13). For example: `docling /workspace/in/X.pdf --output /workspace/out/X_docling.json --to json`.
- Live test cost target: < €0.50 on one paper through all four parsers.
- If a parser fails on a paper, log the error in `parser_runs.run_id` detail and continue with the other three. Do NOT crash the whole pipeline.
