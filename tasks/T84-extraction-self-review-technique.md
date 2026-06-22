# T84 — Extraction self-review technique (reframed from "meta-skills")

## Why
The "add reviewer / caveman / ponytail skills" idea, assessed honestly: those are
**Claude-Code build-time skills** that shape how the *human's* coding agent works —
importing them into palimpsest's runtime skill library conflates two different agents
and dilutes a clean, extraction-purpose system. The **kernel worth keeping** is one
thing: an LLM **self-review of extractions** to lift recall/precision — and that belongs
as an *extraction technique*, not a skill (it's exactly what T74 multipass is about).
Token-frugality (the "caveman" motive) is already handled structurally, so there is no
caveman skill to build.

## Input state
- T74 multipass extraction recall (on the board) — the natural home for this.
- Structural verification already present: SHACL gate, provenance-on-insert,
  `diagnose_run`, `extraction_report`, `graph_summary`.
- Structural token-frugality already present: prompt caching, per-page batching, the
  cheap DeepSeek default, parse-once cache.

## Output state (target)
- A **self-review pass inside the extraction technique** (NOT a separate agent): after
  the first pass, a second constrained pass re-checks dropped / low-confidence items
  against the parser spans (verbatim grounding), aligned with the T35 grounded-GT method
  and T74. Budget-gated like every paid call.
- (Optional, narrow) a one-line system-prompt nudge toward minimal generated
  code/notebooks — the only salvage of "ponytail".

## Explicitly NOT doing (and why — record the decision)
- **No generic reviewer/critic/router agent** — CLAUDE.md anti-pattern ("refuse on
  sight"). Self-review is a *pass*, not an agent role.
- **No caveman output-compression skill** — the token cost is dominated by extraction
  prompts (full-paper projections), not chat replies; and replies go to the human who
  must verify, so terse research output undercuts the "human verifies" thesis. Wrong
  target.
- **No ponytail skill** — minimalism is a prompt nudge, not a skill folder.

## Verification
- On the 5-paper corpus, measure recall/precision of single-pass vs self-review
  (reuse `ab_extract._score` / the T35 grounded GT), like T74.
- Confirm NO new agent role was added (the loop still think→act→observe).
- Spend stays under budget; the self-review pass is metered.

## Will touch
- `src/palimpsest/tools/extract.py` (self-review pass, behind a flag), possibly one
  line of the system prompt.

## Will NOT touch
- No new planner/critic/router agent (CLAUDE.md anti-pattern).
- No compression of human-facing replies; no imported Claude-Code meta-skills.
