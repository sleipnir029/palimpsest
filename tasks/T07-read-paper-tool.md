# T07 — read_paper tool

## Why
The agent needs to load a PDF from disk and access its bytes for SHA-256 hashing and downstream parser dispatch. Required before T15 (cache) and T16 (batch parse).

## Input state
- T06 (agent loop) merged.
- `src/palimpsest/tools/__init__.py` has the TOOLS dict and `register` decorator.

## Output state
- File `src/palimpsest/tools/read_paper.py` exists and:
  - Defines `def read_paper(path: str) -> dict` returning `{"sha256": str, "page_count": int, "bytes_len": int, "path": str}`.
  - Uses `hashlib.sha256` on `Path(path).read_bytes()`.
  - Uses `pymupdf` (`import fitz; fitz.open(path).page_count`) for page count.
  - Is registered in TOOLS via `@register("read_paper", schema={...})` with a JSON Schema matching the Anthropic tool format: `{"name": "read_paper", "description": "Load a PDF and return its SHA-256, page count, and size.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}`.
- File `src/palimpsest/tools/__init__.py` imports `read_paper` so registration fires.
- File `tests/test_read_paper.py` loads `tests/fixtures/sample.pdf` and asserts all four keys with correct types and sane values (sha256 length 64, page_count > 0, bytes_len > 1000).
- File `tests/fixtures/sample.pdf` exists (copy from `papers/` once Rahat has placed at least one PDF there; if `papers/` is empty, this task is blocked).

## Verification
```bash
pixi run pytest tests/test_read_paper.py -v
```
Must exit 0 with 1 PASSED.

## Will touch
- `src/palimpsest/tools/read_paper.py` (new)
- `src/palimpsest/tools/__init__.py` (edit: import read_paper)
- `tests/test_read_paper.py` (new)
- `tests/fixtures/sample.pdf` (new — copy from papers/)

## Will NOT touch
- `src/palimpsest/agent.py`
- Any other tool file.

## Out of scope
- Caching the SHA-256 → T15.
- Triggering remote parsers → T16.
- Provenance tracking → T24.

## Notes / references
- Use `hashlib.sha256()` and `pathlib.Path(path).read_bytes()`.
- `pymupdf` is in pixi.toml; `import fitz` (the pymupdf module is imported as `fitz` for legacy reasons).
- Do NOT add pypdf, pdfminer, pdfplumber, or anything else.
- If `papers/` is empty, document in DEVIATIONS.md and ask Rahat to add a PDF before proceeding.
