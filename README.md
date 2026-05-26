# palimpsest

A custom Python agent that extracts structured, ontology-aligned data from PEM electrolyzer / OER catalyst research papers.

10-credit MSc mini-thesis, RWTH Aachen — Group G03 Earth.

## You are here

```
palimpsest/
├── README.md                    ← you are here
├── SETUP.md                     ← step-by-step setup (read second)
├── CLAUDE.md                    ← rules Claude Code must follow
├── EXECUTION.md                 ← how to run a workday without drift
├── palimpsest-v2-design.md      ← technical design (reference)
├── PROGRESS.md                  ← append one line per merged task
├── DEVIATIONS.md                ← log every time Claude wanders
├── tasks/                       ← 45 task cards (T01–T45)
│   ├── _template.md
│   ├── T01-pixi-init.md
│   └── ... T45-final-demo.md
├── papers/                      ← drop your OER PDFs here
├── src/palimpsest/              ← code goes here (T01 onwards)
├── schema/                      ← LinkML schema (T18 onwards)
├── skills/                      ← SKILL.md files (T20 onwards)
├── docker/                      ← Dockerfile for palimpsest-gpu (T10–T13)
├── notebooks/                   ← marimo notebooks (agent-generated)
├── tests/                       ← pytest + fixtures
├── queries/                     ← SPARQL queries (T40)
├── experiments/                 ← parser benchmarking scripts (T36–T39)
└── thesis/                      ← thesis chapters (T42–T44)
```

## Read order (first session)

1. **This file** (you are here).
2. **SETUP.md** — get the environment working.
3. **CLAUDE.md** — internalize the seven forbidden behaviours.
4. **EXECUTION.md** — internalize the three principles (constrain / verify / audit).
5. **tasks/T01-pixi-init.md** — your first task.

Do NOT read `palimpsest-v2-design.md` cover-to-cover. It's a reference. Look up specific sections (F1–F14, Appendix C, etc.) when a task points to them.

## The one rule

> Close every degree of freedom Claude has *before* it starts coding.

If you internalize that, the rest is mechanics.

## Where to ask for help

- **In-scope for Claude Code:** anything covered by a task card.
- **Out-of-scope for Claude Code:** design changes, schema gaps, dependency conflicts, budget overruns, thesis-defence framing — those go to a fresh design conversation.
