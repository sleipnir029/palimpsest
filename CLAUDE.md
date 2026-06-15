# CLAUDE.md — palimpsest

You are helping Rahat build palimpsest: a small Python agent that extracts
structured data from research pdf (for starting it's using PEM electrolyzer / OER catalyst PDFs) into an
ontology-aligned RDF graph. It is a 10-credit MSc mini-thesis at RWTH.
The whole agent is ~400 lines of Python. Keep it that way.

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
- No LLM gateways (LiteLLM, OpenRouter).
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

### When to stop and ask
- The user mentions a feature not in the F1–F14 list. Confirm before building.
- A change would push total LOC above ~600. Confirm before continuing.
- A change would invalidate the prompt cache mid-session. Confirm.
- A dependency is not in pixi.toml. Confirm before adding.

These guidelines bias toward caution over speed. For trivial tasks, use judgment.
