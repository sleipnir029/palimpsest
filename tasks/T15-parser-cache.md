# T15 — parser_runs SQL + cache helpers

## Why
The parse-once cache is the single biggest budget lever. SHA-256 keys + side-by-side storage of all four parsers' outputs.

## Architecture note
**Unchanged by the four-isolated-images decision** (reviewed, not missed): the cache key is
`(sha256, parser_name)`, which is already per-parser-independent. Whether the four parsers run in
one pod (old design) or one pod per parser (new batch-by-parser design), the rows and helpers are
identical. No edits required here.

## Input state
- T05 merged (SQLite DB exists).
- T07 merged (read_paper produces sha256).

## Output state
- File `src/palimpsest/cache.py` (replacing the empty stub) exports:
  - DDL applied on first init (in addition to T05's tables):
    - `papers(sha256 PRIMARY KEY, filename, added_at, page_count, doi)`
    - `parser_runs(paper_sha256, parser_name CHECK IN ('docling','mineru','chandra','dots','paddle'), parser_ver, parsed_at, output_path, gpu_seconds, gpu_cost_eur, run_id, PRIMARY KEY (paper_sha256, parser_name, parser_ver))` — **5-parser set per T17** (olmocr dropped, dots + paddle added; see PROGRESS T17).
  - Class `ParserCache`:
    - `__init__(self, db_path: str = "palimpsest.db", cache_dir: Path = Path("cache"))`.
    - `def add_paper(self, sha256, filename, page_count, doi=None) -> None`.
    - `def has_all_parsers(self, sha256: str) -> bool` — true iff 5 rows exist for the sha across all 5 parser names.
    - `def get_output(self, sha256: str, parser_name: str) -> Path | None` — returns path to cached output file or None.
    - `def insert_parser_run(self, sha256, parser_name, parser_ver, output_path, gpu_seconds, gpu_cost_eur, run_id) -> None`.
    - `def list_unseen(self, pdfs: list[Path]) -> list[tuple[Path, str]]` — returns `[(path, sha256), ...]` for PDFs missing one or more of the 5 parser outputs.
- File `tests/test_cache.py` covers:
  - Insert paper, insert 5 parser runs, `has_all_parsers` returns True.
  - `get_output` returns the right path.
  - `list_unseen` returns only PDFs needing parsing.

## Verification
```bash
pixi run pytest tests/test_cache.py -v
```

## Will touch
- `src/palimpsest/cache.py` (full implementation)
- `tests/test_cache.py` (new)

## Will NOT touch
- `src/palimpsest/cost.py` (T05 stays as is).
- Any parser file (T16 builds on this).

## Out of scope
- Running parsers → T16.
- Verifying cache hit → T17.

## Notes / references
- Design ref: Appendix C SQL DDL.
- Cache layout: `cache/{sha256}/docling.json`, `cache/{sha256}/mineru.json`, etc. The `output_path` column stores a relative path under `cache_dir`.
- Use stdlib `sqlite3`. No ORM.
- `parser_ver` is a string like `"docling-2.x granite-258M"` — let the parser write its own version string at runtime.
