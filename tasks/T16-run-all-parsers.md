# T16 — run all five parsers, batch-by-parser, with cache

## Why
The parse-once design with five **isolated** parser images: each image runs in its own pod, so
the runner loops parser-first — start one pod per parser, push the whole corpus through it, tear
down, next parser. (Image pull is the dominant RunPod cost; one pull per parser amortizes over
all PDFs.) All caches written, keyed `(sha256, parser)`.

## Input state
- T14 (gpu_provider) + T15 (cache) merged. All five RunPod templates registered (T13/T17).

## Output state
- File `src/palimpsest/parsers/commands.py` — the **parser registry**: a module-level dict
  `PARSERS` mapping each parser name to `{template_id_env, run_cmd}`, where `run_cmd`
  is a function returning the shell command for an input/output path pair (e.g. mineru → `mineru -b vlm ...`).
  (The cache output filename is uniformly `{parser}.json`, so no per-parser `output_name` is needed.)
  One literal dict, ~5 entries — it absorbs the heterogeneity of the five images (different
  entrypoints incl. the baked wrappers `python /opt/dots_run.py` and `python /opt/paddle_run.py`) in one place. Easy to test,
  easy to update when a parser CLI changes.
- File `src/palimpsest/parsers/runner.py` exports:
  - `def parse_with_cache(pdf_paths: list[Path], cost_meter, cache: ParserCache) -> dict[str, dict[str, Path]]`:
    1. For each PDF, compute sha256.
    2. Call `cache.list_unseen(pdfs)`. If all cached, return mapping from cache without starting any pod.
    3. **For each parser** in `PARSERS`:
       - First fill `result[sha][parser]` from cache for every PDF *already cached* for this
         parser (so cached papers still appear in the output — see the invariant in step 5).
       - If no PDF is unseen for this parser, skip the pod entirely.
       - Otherwise `with RunPodSession(cost_meter, template_id=env[PARSERS[parser]["template_id_env"]]) as gpu:`
         and for each `(pdf, sha)` *unseen* for this parser:
         - `gpu.scp_up(pdf, f"/workspace/in/{pdf.name}")`
         - `gpu.ssh(PARSERS[parser]["run_cmd"](f"in/{pdf.name}", f"out/{sha}_{parser}.json"))`
         - `gpu.scp_down(f"/workspace/out/{sha}_{parser}.json", cache_dir / sha / f"{parser}.json")`
         - `cache.insert_parser_run(sha, parser, version, output_path, seconds, cost, run_id)`
    4. `cache.add_paper(sha, filename, page_count)` for each new paper.
    5. Return mapping `{sha: {parser_name: Path}}`. **Invariant:** the mapping is COMPLETE —
       every sha × every parser is present, whether the path came from cache or a fresh run.
- File `tests/test_runner.py` with mocked gpu_provider covers happy path, "all cached"
  short-circuit, and the **mixed/per-parser-skip case** (one parser fully cached, another not) —
  asserting the returned mapping is complete (all shas × all parsers), which is the invariant the
  cached-fill in step 3 protects.

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
assert set(result[sha].keys()) == {'docling','mineru','chandra','dots','paddle'}
print('5 parsers cached for', sha[:12])
"
```
Mocked tests pass. Live invocation produces 5 cached outputs in `cache/<sha>/`.

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
- Live test cost target: < €0.60 on one paper through all five parsers.
- If a parser fails on a paper, log the error in `parser_runs.run_id` detail and continue with the other four. Do NOT crash the whole pipeline.
