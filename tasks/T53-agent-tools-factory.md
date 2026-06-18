# T53 — General agent tools + build_agent factory

**Status:** ✓ done (commit `90f7626`, 2026-06-18). Retroactive card — built from the
agentic-layer plan, not card-first.

## Why
The agent could only call 5 narrow tools (read_paper/read_first_page_text/read_skill/extract/
open_notebook); it could not read arbitrary files, query the graph, or run the pipeline end-to-end
from the TUI. CLI and TUI also duplicated agent construction + a static 2-tool system prompt.

## What was built
- `tools/read_file.py` — read any workspace file; capped (~100K chars) with a truncation marker;
  refuses binary (NUL-byte guard) and points to read_paper for PDFs.
- `tools/list_dir.py` — list a directory (dirs suffixed `/`).
- `tools/sparql_query.py` — wrap `RDFStore("store").sparql(...)` → JSON; read the graph conversationally.
- `tools/run_paper.py` — registers `extract_paper`: one call = parse (cached or GPU) → extract → SHACL
  → provenance insert, metered against the €50 ledger.
- `agent.build_system_prompt(cost_meter)` — dynamic prompt from the `TOOLS` registry + skill manifest
  + live budget; `agent.build_agent(provider, cost_meter)` factory consumed by both entrypoints.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_agent_tools.py -q   # 12 passed
ANTHROPIC_API_KEY="" pixi run pytest -m "not slow" -q               # 196 passed, 0 failures
```

## Touched
- `tools/{read_file,list_dir,sparql_query,run_paper}.py` (new), `tools/__init__.py` (register)
- `agent.py` (build_system_prompt + build_agent), `__main__.py` + `tui/app.py` (use the factory)
- `tests/test_agent_tools.py` (new)

## Out of scope / deferred
- `extract_paper` writes the cwd-relative `store/` + `palimpsest.db` (dev split-brain) — unifying
  paths under a workspace is a portability-phase decision (DEVIATIONS 2026-06-18).
- A `parse_pdf` tool separate from `extract_paper` — only if run_paper's coupling proves too coarse.

## Notes
- Tools are module-level `@register` callables invoked with the LLM's kwargs; `run_paper`/`sparql_query`
  lazy-import the heavy pipeline/store to keep the `tools/__init__` scan cheap.
