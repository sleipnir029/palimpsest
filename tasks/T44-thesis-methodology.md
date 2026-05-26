# T44 — Thesis chapter: methodology + reflection on LLM-assisted development

## Why
Methodological transparency. The thesis must explain how palimpsest was built, with honest reflection on what worked and what didn't.

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
  - Section: Future work — HER/CO2RR/NRR skills, larger corpora, deeper ontology integration.
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
