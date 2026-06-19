# T70 — Agent self-diagnosis: act on extraction drops at run time

**Status:** planned · **Group:** constrained-autonomy (thesis core) · **Priority:** high

## Bigger picture (read first)
This is the sharpest version of the meeting's autonomy question and the thesis's lead
claim: **move the correction competence from build-time (human + Claude Code reading
logs) into the running agent.** Documented build-time catches — the enum-drop bug
(T50, caught by an independent reviewer subagent), the F2 skill drift — were all fixed
by *people*, never by the agent noticing. T58 (done) already gives the agent *eyes*
(it can call `extraction_report` to see drops + reasons). What's missing is the agent
*using* those eyes in the loop to diagnose and react. That step is the run-time
autonomy contribution. See `report/supervisor-answers-2026-06-19.md` §2 (mechanism #4)
and the plan `~/.claude/plans/so-i-had-a-snappy-lark.md`.

**Hard constraint (CLAUDE.md anti-pattern):** NO planner / critic / router agent. This
must be in-loop guidance + a read-only diagnostic helper that the *existing* single
agent loop consumes — not a second agent and not an unsupervised re-extraction loop
that spends budget on its own.

## Why
After an extraction run with drops, the agent currently moves on. A human has to read
`extraction_report` to notice that, say, 8 of 11 drops are the same `unit V≠mV` error
(a systematic prompt/skill problem) versus 1 random mis-citation (noise). The agent
should surface that distinction itself and recommend the right action.

## Current situation
- `extract()` returns `(valid, errors)`; `errors` carries per-item reasons (mis-cite
  digit guard, unit mismatch, missing evidence, unknown class, Pydantic).
- **T58 done:** `extraction_report(pdf|sha, parser)` reads the latest run's dropped
  items + human-readable reasons; `runs.py` (`ExtractionRunLog`) persists counts +
  (per T58) reasons. `workspace_status` shows the count.
- **Gap:** nothing summarizes drop *patterns*, and nothing in the agent loop prompts
  the agent to inspect the report and decide. Correction was explicitly T58-out-of-scope.

## What to build
1. **A read-only pattern summarizer** — extend `extraction_report` or add
   `diagnose_run(pdf|sha, parser)` that buckets the run's drops by reason and flags
   systematic ones (e.g. "8/11 drops = unit mismatch → systematic; 1 mis-citation =
   noise") with a recommended action per bucket (re-extract / fix skill alignment /
   accept as noise). Pure summary over `ExtractionRunLog`; no LLM, no spend.
2. **In-loop guidance** — when a `run_paper`/`extract` tool result reports drops, its
   returned text nudges the agent to call `diagnose_run` and act. The agent (not new
   control code) decides whether to re-extract a page, flag a systematic issue to the
   human, or proceed. Keep the nudge minimal and provider-agnostic.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_diagnose_run.py -q
# seeded run log with 8 unit-mismatch + 1 mis-citation drop → diagnose_run reports the
# unit mismatch as systematic with a re-extract/skill-fix recommendation.
# (optional, --live) e2e: agent given a drop-heavy run calls diagnose_run + surfaces the pattern.
```

## Will touch
- `src/palimpsest/tools/extraction_report.py` (extend) or new `tools/diagnose_run.py`
  + `tools/__init__.py`
- `src/palimpsest/runs.py` (read helpers if needed; do NOT duplicate the store)
- `src/palimpsest/tools/run_paper.py` / `extract.py` tool-result text (the nudge)
- `tests/test_diagnose_run.py` (new)

## Out of scope
- Unsupervised auto-re-extraction loops (budget risk) — recommend, let the human/agent
  trigger, don't auto-spend.
- A second "critic" agent — forbidden; this is in-loop guidance only.
- Auto-editing the skill to fix a systematic issue → surface it; editing is T69/T71 work.
