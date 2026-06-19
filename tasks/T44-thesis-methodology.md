# T44 — Thesis chapter: methodology + reflection on LLM-assisted development

**Status:** planned (writing) · **Group:** thesis · **Priority:** medium

> **Updated 2026-06-19 — the spine of this chapter is the build-time→run-time reframe.**
> The thesis contribution is the **constrained-autonomy agent**, and the honest
> methodological story is: palimpsest's competence on OER was, during construction,
> repeatedly supplied by a *human + Claude Code + reviewer subagents* patching the engine
> — NOT by the agent self-correcting. Use the documented build-time catches as evidence,
> stated plainly:
> - the enum-mismatch → 0-valid-extractions bug, and the follow-on where the modelled
>   enums were **silently dropped at insert** — caught by an **independent reviewer
>   subagent** (T50), then pinned with a correlated SPARQL regression test;
> - the F2 skill-table drift pointing at deleted schema slots — caught by a human reviewer.
> The reflection's thesis: the safety net was build-time review; the contribution
> (T62/T69/T70) is **moving that competence into the running agent** so a new domain
> doesn't need Claude Code present. Retire the "domain-agnostic" claim (see
> `report/supervisor-answers-2026-06-19.md` §0); claim autonomy *within an authored
> domain* + a documented skill-creation method. Cross-ref the supervisor-answers doc.

## Why
Methodological transparency. The thesis must explain how palimpsest was built, with honest reflection on what worked and what didn't — and, centrally, on where the *agent's* autonomy ended and the *builder's* intervention began.

## Input state
- DEVIATIONS.md populated across all 5 weeks.
- PROGRESS.md complete.

## Output state
- File `thesis/04_methodology.md` containing:
  - Section: System architecture (1-page overview with a figure of the loop + tools + cache + store).
  - Section: Implementation approach — the task-card / restate-before-code methodology from EXECUTION.md.
  - Section: Cost and time accounting — total spend, total hours, breakdown.
  - Section: Reflection on LLM-assisted development:
    - What worked: tight task cards, restate-before-code, the diff audit.
    - What didn't: examples from DEVIATIONS.md.
    - When does Claude Code drift? Patterns observed.
    - When does it shine? Tasks with clear verification commands.
  - Section: Limitations of the system.
  - Section: Future work — additional domain skills (HER/PEMWE done as T71; CO2RR/NRR next), larger corpora, and deepening run-time autonomy (the T62/T69/T70 mechanisms toward an agent that onboards a domain with less human review).
- Word count: 2500–4000 words.

## Verification
```bash
test -f thesis/04_methodology.md
wc -w thesis/04_methodology.md
```

## Will touch
- `thesis/04_methodology.md` (new)

## Will NOT touch
- DEVIATIONS.md, PROGRESS.md (those are stable refs).

## Out of scope
- Comparison with other extraction frameworks (out of scope; mention as related work).

## Notes / references
- This chapter is unusual: a thesis that reflects on its own construction process. Embrace it.
- Be honest. If something didn't work, say so. Examiners value rigor over polish.
- 3 hours.
