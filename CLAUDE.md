# CLAUDE.md — palimpsest

You are helping Rahat build palimpsest: a Python **autonomous research agent**
that, spawned in a workspace (like Claude Code), turns research PDFs (starting
with PEM electrolyzer / OER catalyst papers) into a queryable, ontology-aligned
RDF graph — parsing, extracting, editing notebooks/markdown/data/schema, running
the pipeline, and querying, with the human supervising and verifying. It is a
10-credit MSc mini-thesis at RWTH. The **thesis contribution is the constrained-
autonomy agent** (parser-conditional extraction accuracy is one section, not the
whole). Keep each piece minimal, but the agent layer is intentionally larger than
the original extraction-only core — don't shrink it back to a one-shot extractor.

## 1. Think before coding
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them. Do not pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what is confusing. Ask.

## 2. Simplicity first
- Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that was not requested.
- If you write 200 lines and it could be 50, rewrite it.
- Ask: "would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical changes
- Touch only what you must.
- Do not "improve" adjacent code, comments, or formatting.
- Do not refactor things that are not broken.
- Match existing style, even if you would do it differently.
- Clean up only your own mess.

## 4. Goal-driven execution
- Given a goal and success criteria, loop until verified.
- Run the tests yourself before claiming done.
- If a verification step fails, name the failure and fix it.

## Project rules (override the four above when they conflict)

### Stack — locked
- Python 3.11, pixi. macOS arm64 primary dev.
- LLM access via the Anthropic SDK. **Default runtime model: DeepSeek `deepseek-v4-flash`** (T50, 2026-06), called through DeepSeek's Anthropic-compatible endpoint (`https://api.deepseek.com/anthropic`) for cost — Anthropic (Sonnet) is too expensive for iterative runs. `AnthropicProvider` is kept as the fallback; Gemini SDK fallback also allowed. No third-party SDKs beyond these.
- No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen, smolagents, pydantic-ai).
- No MCP servers. Python function calls only.
- No LLM gateways (LiteLLM, OpenRouter) **in the agent loop / orchestration**. The loop
  is locked to the Anthropic wire format and calls DeepSeek/Anthropic directly — a gateway
  must never drive orchestration. **Extraction carve-out (user-authorized 2026-06-22):**
  the EXTRACTION pass MAY route through OpenRouter (OpenAI-compatible, one key) for model
  breadth — `/use extraction openrouter`, model via `OPENROUTER_MODEL`. Budget invariant
  holds: set `OPENROUTER_PRICE_IN`/`OPENROUTER_PRICE_OUT` (USD per 1M tokens) for accurate
  metering, else it falls back to conservative Sonnet rates so the €-cap is never
  under-counted. The earlier T72 benchmark carve-out (`experiments/llm_matrix.py`) stands.
  Claude still runs direct (OpenRouter 2x-marks-up Claude); no gateway drives the loop.
- pyoxigraph for RDF. SQLite for cache + CostMeter. dulwich for versioning.
- LinkML for schema. EMMO ECHO + QUDT + PROV-O + palimpsest-local IRIs.
- Textual + Rich + Typer for TUI. FastAPI + vendored PDF.js + HTMX for viewer.
- marimo for notebooks (spawned by the agent, never auto-executed).

### Budget — €50 hard cap
- CostMeter must be checked before every paid API call.
- €10 → smalle warn in TUI, €20 → mideum warn in TUI, €30 → hige warn in TUI, €40 → highest warn in TUI. €50 → refuse to call. `/budget N` raises the cap live.
- The Claude Code subscription used to BUILD palimpsest is separate from the
  €50; the €50 is what palimpsest itself spends when it runs.

### Parsers — all five, cloud only
- docling, MinerU, Chandra, dots.ocr, PaddleOCR all run on RunPod; GPU is chosen dynamically from availability.
- Local CPU is pymupdf4llm + GROBID for cheap lookups only, NOT in the comparison.
- Parse-once cache by SHA-256 of PDF bytes is mandatory. Never re-parse.

### Provenance — non-negotiable
- Every triple inserted into pyoxigraph carries (paper_hash, parser, page, bbox, run_id).
- If you cannot attach provenance, do not insert the triple and raise it loudly.

### Schema — extensible by file, not by code
- New extraction domains (HER, CO2RR) ship as new SKILL.md folders.
- New slots: propose in `schema/exploratory.yaml`, never silently add to main schema.

### Anti-patterns — refuse on sight
- Adding a planner / critic / router agent.
- Adding LangGraph "because it makes the flow clearer."
- Exposing parsers as MCP servers.
- Vector search "for retrieval."
- Celery, Redis, Postgres.
- A web UI beyond the single-page provenance viewer.
- Running docling locally on M1.

### Constrained-autonomy policy (the thesis core — enforced in code)
- The agent is spawned in a **workspace root** (`$PALIMPSEST_WORKSPACE`, default
  gitignored `./workspace` in dev). It reads freely; `write_file`/`edit_file` are
  **confined to the workspace in code** (`src/palimpsest/policy.py`) — the engine
  (`src/palimpsest/`) and this repo's fixtures (`store/`, `cache/`, `papers/`,
  schema) are off-limits because they're *outside the workspace*.
- The RDF graph + cost ledger are written **only via the pipeline** (provenance +
  budget enforced); `write_file` refuses them even inside a workspace.
- `bash` is a **supervised escape hatch** (Claude Code model): cwd-pinned + a
  foot-gun spend guard, but NOT filesystem-fenced. Don't claim otherwise. Budget
  is enforced in-process; bash subprocess spend is the human's responsibility.
- New agent tools register via `@register` in `src/palimpsest/tools/`; build the
  agent through `agent.build_agent()` (CLI + TUI share it) — don't re-duplicate.

### When to stop and ask
- The user mentions a feature not in the F1–F14 list. Confirm before building.
- A change would invalidate the prompt cache mid-session. Confirm.
- A dependency is not in pixi.toml. Confirm before adding.
- A change would weaken a code-enforced invariant (workspace confinement,
  provenance-on-insert, the €-budget gate). Confirm and re-review.

These guidelines bias toward caution over speed. For trivial tasks, use judgment.
