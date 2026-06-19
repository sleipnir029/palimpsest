# T72 — LLM breadth-matrix extraction benchmark (frontier / cheap / small-open / local)

**Status:** planned · **Group:** evaluation (thesis) · **Priority:** high

## Bigger picture (read first)
The meeting asked for an LLM benchmark across Claude / DeepSeek / Gemini / OpenAI with
DeepEval. After assessing the code with the user, the design is sharper and cleaner:
- **Scoring is deterministic** (recall/precision/F1 on numeric values within tolerance),
  NOT DeepEval — DeepEval's LLM-judge metrics fit free-text/RAG, not numeric extraction,
  and using an LLM to grade LLMs is mildly circular. (`ab_extract.py` already scores
  this way.) Mention DeepEval in the thesis; use it at most as a secondary cross-check.
- **The interesting claim is breadth, not just frontier ranking:** *does structured
  scientific extraction even require a big model, or can a small/local model recover the
  same numbers cheaply?* A "yes, small models suffice" result feeds the FAIR / budget /
  reproducibility argument directly.
- **Critical architecture fact (verified):** the agent loop is locked to the
  Anthropic wire format (`providers/anthropic.py` reads Anthropic `content`/`usage`;
  DeepSeek works only via its Anthropic-compatible endpoint). Driving the *agent* with
  Gemini/OpenAI would need per-provider tool-call translation — **avoid that.** But
  **extraction is already non-agentic**: `extract.py` calls `provider.complete(...,
  tools=None)` then parses `resp.text` as JSON. So we benchmark *extractors*, not agent
  drivers — a thin completion adapter per provider is all that's needed.
See `report/supervisor-answers-2026-06-19.md` §1b/§1c and the plan.

## Why
Quantify the accuracy-vs-cost frontier of extraction across model tiers on the same
ground truth, so the thesis can recommend a model (likely: a cheap/small one) with
evidence, not assertion.

## Model matrix (decided 2026-06-19; cost is a REPORTED axis, not a footnote)
Per-paper extraction ≈ 25K input + 3K output tokens. The price *spread* is the finding.
Claude IDs + pricing are authoritative (from the claude-api reference, 2026-06-04);
**non-Anthropic/non-DeepSeek IDs + pricing must be verified at run time** — do NOT bake
guessed numbers in.

| Provider | Model | ID | $/M in·out | ~€/paper | Role |
|---|---|---|---|---|---|
| Anthropic | Haiku 4.5 | `claude-haiku-4-5` | 1 / 5 | ~0.04 | **headline small-frontier probe** |
| Anthropic | Sonnet 4.6 | `claude-sonnet-4-6` | 3 / 15 | ~0.11 | mid frontier |
| Anthropic | Opus 4.8 | `claude-opus-4-8` | 5 / 25 | ~0.19 | frontier ceiling (run once; optional) |
| DeepSeek | v4-flash | `deepseek-v4-flash` | 0.14 / 0.28 | ~0.004 | cheapest cloud (agent default) |
| DeepSeek | v4-pro | (see `ab_extract.py`) | — | ~0.013 | within-provider small-vs-big |
| Gemini | flash tier | verify at runtime | — | low | Google cheap rep (Gemini SDK allowed) |
| OpenAI | one mini + one frontier | verify at runtime | — | — | breadth (httpx OpenAI-compat adapter) |
| Qwen | 7B + 32B | verify (OpenAI-compat endpoint) | — | low | small open-weight |
| Local | Qwen-7B / Llama-8B | Ollama on the M1 | €0 (compute) | €0 | free/local floor |

Headline argument: **if Haiku 4.5 (1/5 of Opus's price) — or DeepSeek-flash (~50× cheaper)
or a local Qwen-7B (free) — matches Opus on numeric extraction, the "no big model needed"
claim stands.** Plot accuracy (recall/precision/F1) vs €/paper; cost is the x-axis.
Whole matrix over ~5 GT papers is a few € — well under the €50 cap.

## Current situation
- `experiments/ab_extract.py`: deterministic recall/precision scorer, DeepSeek
  flash-vs-pro, single paper. Reuse its matching/scoring logic.
- `providers/`: `anthropic.py` (Anthropic wire) + `deepseek.py` (subclass, compat
  endpoint). No Gemini, no OpenAI-compatible adapter.
- `httpx` is already in `pixi.toml` → OpenAI-compatible endpoints (OpenAI, Qwen via
  DashScope/Together, local Ollama/vLLM/llama.cpp) can be hit **without a new SDK**,
  so no locked-stack break; this is experiment-only code.
- Ground truth: 5 papers (OER) grounded (T35). For a hydrogen-domain matrix, reuse
  T73's labeled subset.

## What to build
1. **~3 extraction adapters**, each exposing `complete(system, messages, tools=None)
   -> LLMResponse(text, usage, tool_calls=[])` and mapping token usage for cost:
   - Anthropic-wire (Claude, DeepSeek) — exists.
   - `providers/openai_compat.py` (new, `httpx`) — parameterized by `base_url` +
     `model` + key; covers GPT, Qwen, and local servers. Raise on `tools` (extraction-
     only, NOT an agent driver).
   - `providers/gemini.py` (new) — Gemini SDK (stack-allowed) or its OpenAI-compatible
     endpoint via the same adapter.
2. **`experiments/llm_matrix.py`** — for each model × each paper, run extraction
   (`tools=None`), score against ground truth with the `ab_extract` logic, record
   recall/precision/F1 + €/paper + latency → `experiments/llm_matrix.csv`. Log model
   versions + prompt hash + seeds for reproducibility.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_openai_compat.py -q   # adapter: stub HTTP → text+usage; raises on tools
pixi run python experiments/llm_matrix.py && test -f experiments/llm_matrix.csv
```

## Will touch
- `src/palimpsest/providers/openai_compat.py` (new), `providers/gemini.py` (new),
  `providers/__init__.py`
- `experiments/llm_matrix.py` (new), `experiments/llm_matrix.csv` (generated)
- `tests/test_openai_compat.py` (new)

## Will NOT touch
- `agent.py` / the agent loop (stays DeepSeek; no tool-call wire translation)
- `extract.py` (the `tools=None` path is reused unchanged)

## Out of scope
- Making non-Anthropic-wire models drive the agent loop (explicitly excluded).
- DeepEval as the primary metric (deterministic scorer is primary; DeepEval optional
  secondary cross-check only).
