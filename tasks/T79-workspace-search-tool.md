# T79 — Workspace search tool

## Why
The agent could only grep via the `bash` escape hatch. A first-class, structured,
read-only search tool is table-stakes and keeps power use out of the shell.

## Input state
- 18 tools; no search/grep; `list_dir` was the only discovery tool.

## Output state (delivered)
- `search(pattern, path=".")` — stdlib regex over workspace text files via `os.walk`
  (no ripgrep dependency), capped at 100 hits, returning `relpath:line: text`.
- Read-only and workspace-bounded (`policy.workspace_root`). Skips secret files
  (`policy.is_secret_path`: `.env`/`config.txt`/`*.key`) so a search can never surface
  a secret — preserving the same redaction discipline the session transcript uses.
- Registered via `@register` like every other tool.

## Verification
`pixi run pytest tests/test_search_tool.py -q`
- `test_search_finds_matches`, `test_search_skips_secret_files`,
  `test_search_no_matches`, `test_search_bad_regex`,
  `test_search_rejects_path_outside_workspace`

## Will touch
- `src/palimpsest/tools/search.py` (new), `src/palimpsest/tools/__init__.py` (register)

## Will NOT touch
- The workspace write fence; other tools.
