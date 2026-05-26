# EXECUTION.md — running Claude Code on palimpsest without drift

This is the operational layer on top of `CLAUDE.md` and `palimpsest-v2-design.md`. CLAUDE.md is the constitution; this document is the playbook for *how a single workday actually goes*.

The whole project compresses to one rule:

> **Close every degree of freedom Claude has *before* it starts coding.**

Every choice Claude must make (which file? what name? what behavior on the edge case? validate or trust input?) is a wormhole it can wander into. Tighter specs → fewer wormholes → less drift.

---

## Part 1 — The three principles

### 1. Constrain inputs

Each task is a one-page card committed to `tasks/T##-name.md` *before* Claude opens it. The card declares:

- **Why** the task exists
- **Input state** (what's true before)
- **Output state** (what's true after)
- **Verification** (a literal shell command that must succeed)
- **Will touch** (exact file list)
- **Will NOT touch** (files Claude might be tempted to touch)
- **Out of scope** (things this task is *not*, with pointers to the tasks that will cover them)

Writing task cards is your real planning work. Spend an evening at the start of each week writing all of that week's cards. The cards are the spec; the code that follows them is mechanical.

### 2. Verify understanding before code

Claude *restates the task in three lines* and *lists files it will touch and not touch* before writing any code. If the restatement is wrong, you fix the task card (not the code) and Claude restates again. "Go" is a deliberate handoff, not an implicit start.

### 3. Audit outputs ruthlessly

After every task:

```
git diff --stat                            # is the scope right?
pixi run <verification-command>            # paste verbatim output
git log -1 --format="%s%n%n%b"             # is the message accurate?
```

Reject any commit that adds files not on the `will-touch` list, adds deps not in `pixi.toml`, or says "and also". Force a `git reset --hard` and a re-run with a tighter spec. **Letting one bad commit through is the start of accumulated drift.**

---

## Part 2 — The task card template

Save this as `tasks/_template.md` and copy it for each new task.

````markdown
# T## — <short kebab-case name>

## Why
One sentence on why this task exists. What does it unlock?

## Input state
- T<prev> is merged.
- The repo has <existing files/state>.
- <Anything else that must be true>.

## Output state
- File `<path>` exists and exports `<symbol>` with signature `<sig>`.
- `<some behavior>` works when invoked as `<command>`.
- One test at `tests/<path>` covers the happy path.

## Verification
```
pixi run pytest tests/<file> -v
# OR
pixi run python -c "<one-liner that prints success>"
```
The verification command MUST exit 0 and produce specific output for the task to be done.

## Will touch
- `src/palimpsest/<file>` (new)
- `src/palimpsest/<other>` (edit: <what change>)
- `tests/<file>` (new)

## Will NOT touch
- Any file in `src/palimpsest/parsers/`
- `CLAUDE.md`
- `pixi.toml` (unless explicitly listed)
- `palimpsest-v2-design.md`

## Out of scope
- <related-thing-1> → T## later
- <related-thing-2> → T## later

## Notes / references
- Pattern: see Anthropic cookbook `patterns/agents/basic.py`
- Design ref: §F2 of palimpsest-v2-design.md
````

### Worked example

````markdown
# T07 — read_paper tool

## Why
The agent needs to load a PDF from disk and access its bytes for SHA-256 hashing
and downstream parser dispatch. Required before T15 (cache) and T16 (batch parse).

## Input state
- T06 (agent loop) is merged.
- Repo has `src/palimpsest/agent.py`, `src/palimpsest/tools/__init__.py` with empty TOOLS dict.
- No `read_paper.py` yet.

## Output state
- File `src/palimpsest/tools/read_paper.py` exists and exports
  `def read_paper(path: str) -> dict` returning
  `{"sha256": str, "page_count": int, "bytes_len": int, "path": str}`.
- Registered in `src/palimpsest/tools/__init__.py` TOOLS dict under key "read_paper".
- One test at `tests/test_read_paper.py` loads `tests/fixtures/sample.pdf`
  and asserts all four keys exist with the right types.

## Verification
```
pixi run pytest tests/test_read_paper.py -v
```
Must exit 0 with one PASSED.

## Will touch
- `src/palimpsest/tools/read_paper.py` (new)
- `src/palimpsest/tools/__init__.py` (edit: add "read_paper" entry to TOOLS)
- `tests/test_read_paper.py` (new)
- `tests/fixtures/sample.pdf` (new — copy from `papers/s41467-022-35426-8.pdf`)

## Will NOT touch
- `src/palimpsest/agent.py`
- Any file in `src/palimpsest/providers/`
- Any file in `src/palimpsest/parsers/`
- `CLAUDE.md`, `pixi.toml`, `palimpsest-v2-design.md`

## Out of scope
- Caching of the hash → T15
- Triggering remote parsers → T16
- Provenance tracking → T24

## Notes / references
- Use `hashlib.sha256()` on `Path(path).read_bytes()`.
- Use `pymupdf` (already in pixi.toml) for page_count via `fitz.open(path).page_count`.
- Do NOT use pypdf, pdfminer, or anything not in pixi.toml.
````

This card is ~40 lines. The code that satisfies it is ~25 lines. The ratio feels heavy until you remember: this is the cost of *not* having to debug or unwind drift later.

---

## Part 3 — The conversation patterns

### Opening prompt (copy verbatim for each task)

```
You're working on palimpsest. Read these files in order and STOP:

1. CLAUDE.md
2. tasks/T07-read-paper-tool.md
3. PROGRESS.md — last 5 lines only

After reading:
1. Restate the task in exactly 3 lines: input, output, verification.
2. List the files you will touch (and confirm they match the card).
3. List the files you will NOT touch.
4. Wait for my explicit "go" before writing any code.

Do not read palimpsest-v2-design.md unless I ask. Do not read other source files
unless the task card lists them. Do not run shell commands yet.
```

This gate catches misunderstanding *before* you've committed time to it. If the restatement is wrong, you have two options:

- **The card is wrong.** Edit the card, commit the edit, ask Claude to re-read and restate.
- **Claude misread.** Say "re-read tasks/T07 — note that [specific thing]". Restate again.

You almost never proceed without a clean restatement. The five minutes you spend here saves an hour of unwinding.

### Mid-task interventions

If Claude says "while I'm here, let me also..." → **stop immediately**:

> Out of scope. Only the items in the task card. If you think this needs doing, name it and I'll add a task for it.

If Claude says "I'll add a small helper function for ..." → check if that helper is justified by the task. If not:

> Inline it or remove it. No new abstractions in this task.

If Claude says "I'll use [library X] for this" and X isn't in pixi.toml:

> Stop. Verify with `pixi run python -c "import X"`. If it fails, do not add it — find another way using the locked dependencies.

If Claude says "the test passes" without showing output:

> Paste the verbatim output of `pixi run pytest tests/test_read_paper.py -v` — nothing else.

### Closing prompt (copy verbatim when Claude says it's done)

```
Before I review, complete this checklist literally:

1. Paste the verbatim output of: pixi run <verification-command>
2. Paste the verbatim output of: git diff --stat
3. Did you touch any file not on the "will touch" list in the task card? If yes, list it.
4. Did you add any dependency not already in pixi.toml? If yes, name it.
5. Did you write any code, even a one-liner, that doesn't directly satisfy the task card? If yes, name it.
6. Did any test fail or get skipped? If yes, paste the failure.

Do not write a summary. Do not commit yet. Wait for my "merge".
```

Read each answer literally. Cross-check against the task card. Then either:

- **All clean** → "merge" → Claude commits with the message format below, then updates `PROGRESS.md` with one line.
- **Anything off** → tell Claude exactly what to undo. If significant, `git reset --hard` and re-run from the opening prompt with a tighter card.

### Commit message format

```
<area>: T<##>: <one-line summary>

<optional body, max 3 lines explaining non-obvious choices>

Refs: tasks/T<##>-<name>.md
```

Examples:

```
agent: T06: minimal think→act→observe loop with one tool slot
parsers: T14: gpu_provider context manager with idle watchdog
schema: T18: LinkML schema with EMMO+QUDT+palimpsest IRIs for OER slots
```

`git log --oneline` becomes a chronological thesis chapter.

---

## Part 4 — PROGRESS.md format

A single file at the repo root, append-only during development. Claude updates it with one line per completed task.

```markdown
# palimpsest progress

## Week 1 — foundations
- T01 ✓ 2026-05-28  pixi init, lockfile committed, M1 clean install verified
- T02 ✓ 2026-05-28  repo skeleton from Appendix B (16 dirs, 0 files of code)
- T03 ✓ 2026-05-28  CLAUDE.md committed verbatim from Appendix A
- T04 ✓ 2026-05-29  AnthropicProvider class, smoke-tested against claude-sonnet-4-5
- T05 ✓ 2026-05-29  CostMeter + SQLite ledger + check_or_raise + /budget live update
- T06 ✓ 2026-05-30  agent loop with cache_control on system+tools, 78 LOC
- T07 ✓ 2026-05-30  read_paper tool
- T08 ✓ 2026-05-31  end-to-end smoke: "what is the title?" → correct title via 1 LLM call

## Week 2 — parsing & cache
- T09 ⏳ in progress
- T10 …
```

Status markers: `✓` done & merged, `⏳` in progress, `⏭` skipped (with reason), `🔁` redone (with reason). That's it. No prose, no celebration — just the wall of green checkmarks.

When you open Claude Code in the morning, the first thing you do is read the last 5 lines of `PROGRESS.md`. The last thing you do at night is verify the day's lines are accurate.

---

## Part 5 — The deviations log

A second file at the repo root: `DEVIATIONS.md`. Append-only. Every time Claude does something unexpected — good or bad — log it.

```markdown
# Deviations log

## 2026-05-29 — T05
**What:** Claude wanted to add a `cost_meter.export_csv()` method "for thesis plots later".
**Verdict:** Rejected. Out of scope for T05. Added to backlog as T-future-A.
**Lesson:** "useful later" is always a deferral, never an inclusion.

## 2026-05-30 — T06
**What:** Claude assumed `anthropic.messages.create` accepts `cache_control` as a top-level kwarg; it's a per-block field. Test failed with TypeError.
**Verdict:** Fixed in second attempt after I pointed at the cookbook example. Confirmed by paste of `python -c "import anthropic; print(anthropic.__version__)"` = 0.40.x.
**Lesson:** When using a feature added in a specific SDK version, paste the SDK version into the task card next time.

## 2026-05-31 — T08
**What:** Test "passed" but Claude hadn't actually run it; it inferred from reading the code.
**Verdict:** Reset, re-ran with explicit "paste verbatim pytest output". Tests then failed (mock not wired); fixed.
**Lesson:** Always require verbatim output. Never accept "tests pass" as a textual claim.
```

After the project, this file is one of the most valuable artifacts: it's the reflection chapter of your thesis on what working with LLM coding agents is actually like. Build it deliberately.

---

## Part 6 — The 45-task breakdown

Five weeks, ~45 atomic tasks. Each is sized for a 30–90 min session. Write the cards in `tasks/` *one week at a time*, on the Sunday before the week starts.

### Week 1 — foundations (~6 hours total)

| # | Code | Title | Est | Verifies |
|---|------|-------|-----|----------|
| 1 | T01 | pixi init + lockfile | 45m | `pixi install && pixi run python -c "import palimpsest"` succeeds on fresh clone |
| 2 | T02 | repo skeleton from Appendix B | 30m | `tree src/palimpsest` matches Appendix B exactly |
| 3 | T03 | commit CLAUDE.md from Appendix A | 15m | file exists, 96 lines, hash matches |
| 4 | T04 | AnthropicProvider class | 45m | smoke call to claude-sonnet-4-5 returns text |
| 5 | T05 | CostMeter + SQLite ledger + /budget live update | 60m | `pixi run pytest tests/test_cost.py` passes; `/budget 75` updates `settings` row |
| 6 | T06 | agent loop with cache_control | 60m | 78–100 LOC; one round-trip with `cache_read_input_tokens > 0` on second call |
| 7 | T07 | read_paper tool | 30m | tests/test_read_paper.py passes |
| 8 | T08 | end-to-end smoke: "title of this paper?" | 45m | correct title for sample.pdf via 1 LLM call, cost logged |

### Week 2 — parsing & cache (~8 hours)

| # | Code | Title | Est | Verifies |
|---|------|-------|-----|----------|
| 9 | T09 | RunPod account + API key + manual test pod | 30m | one pod started & stopped manually; bill < $0.05 |
| 10 | T10 | Dockerfile: docling + granite-docling-258M baked | 60m | `docker run … docling --version` on RTX 4090 |
| 11 | T11 | Dockerfile: MinerU 2.5 with weights baked | 45m | image lists MinerU2.5-2509-1.2B in `pip list` |
| 12 | T12 | Dockerfile: olmOCR-2-7B-1025 baked | 45m | image runs `olmocr --version` |
| 13 | T13 | Dockerfile: Chandra 2 (4B) baked | 45m | image runs `chandra --version` |
| 14 | T14 | gpu_provider context manager + idle watchdog | 90m | `with RunPodSession() as s: …` starts/stops pod, logs cost |
| 15 | T15 | parser_runs SQL schema + cache helpers | 60m | tests/test_cache.py exercises insert/lookup by sha256 |
| 16 | T16 | run_all_parsers on one PDF, one session | 90m | 4 outputs written under cache/{sha}/{parser}.json; rows inserted |
| 17 | T17 | cache hit on second invocation | 30m | second call to `parse_with_cache` makes 0 GPU calls; verified by ledger |

### Week 3 — schema & extraction (~7 hours)

| # | Code | Title | Est | Verifies |
|---|------|-------|-----|----------|
| 18 | T18 | LinkML schema with EMMO+QUDT+palimpsest IRIs | 90m | `pixi run linkml-validate schema/palimpsest.yaml` clean; ontology.py resolves all EMMO hashes |
| 19 | T19 | schema generation pipeline | 45m | `pixi run schema` produces pydantic + shacl + jsonld with 0 errors |
| 20 | T20 | skills/oer-extraction/SKILL.md | 60m | YAML frontmatter validates; body covers all schema slots |
| 21 | T21 | skill loader (`read_skill` tool) | 30m | tests show progressive disclosure: only frontmatter in system, body loaded on demand |
| 22 | T22 | extraction tool: parser → Sonnet → Pydantic | 90m | 1 paper → ≥5 validated Pydantic instances |
| 23 | T23 | SHACL validation step | 30m | invalid instance rejected with concrete violation message |
| 24 | T24 | pyoxigraph insert + provenance triples | 60m | each measurement triple has wasDerivedFrom + page + bbox |
| 25 | T25 | end-to-end: 1 paper → graph + SHACL pass | 60m | one SPARQL query returns expected overpotential |

### Week 4 — UI & viewer (~8 hours)

| # | Code | Title | Est | Verifies |
|---|------|-------|-----|----------|
| 26 | T26 | Textual chat skeleton | 60m | `pixi run tui` opens chat screen; cost meter visible top-right |
| 27 | T27 | slash command dispatcher | 45m | `/help`, `/quit` work; unknown slash → friendly error |
| 28 | T28 | /budget, /cost, /model | 60m | `/budget 75` updates DB; `/cost` shows ledger summary; `/model haiku` switches provider |
| 29 | T29 | FastAPI viewer skeleton with PDF.js | 90m | `pixi run viewer` serves PDF at localhost:8765 |
| 30 | T30 | /paper/{sha}/data JSON endpoint | 45m | returns validated extracted triples with bboxes |
| 31 | T31 | HTMX bbox highlight on hover | 90m | hovering a value highlights the bbox on the PDF page |
| 32 | T32 | open_notebook tool with marimo subprocess | 45m | `marimo edit notebooks/<name>.py --headless --port 0` launches, port returned |
| 33 | T33 | marimo template with SPARQL cell | 60m | template runs against the store, shows overpotential bar chart |

### Week 5 — experiments & writing (~25 hours, mostly writing)

| # | Code | Title | Est | Verifies |
|---|------|-------|-----|----------|
| 34 | T34 | 4-way parse on full 25-paper corpus | 2h | 100 parser_runs rows; total GPU cost logged |
| 35 | T35 | hand-label 5-paper subset (ground truth) | 4h | tests/ground_truth/*.json with verified slot values |
| 36 | T36 | parser metric: text accuracy | 60m | CSV `experiments/text_accuracy.csv` with per-parser % |
| 37 | T37 | parser metric: table-cell F1 | 90m | CSV with per-parser F1 |
| 38 | T38 | parser metric: bbox precision | 60m | CSV with IoU @ 0.5 per parser |
| 39 | T39 | downstream extraction accuracy by parser | 90m | CSV with extraction accuracy conditional on parser |
| 40 | T40 | SPARQL queries for thesis chapters | 60m | 5 named queries with documented results |
| 41 | T41 | plots in marimo notebooks | 90m | 4 plots in `notebooks/thesis_*.py`, exportable as PNG |
| 42 | T42 | thesis chapter: parser comparison | 4h | Markdown chapter + tables + plots |
| 43 | T43 | thesis chapter: ontology gap analysis | 3h | Markdown chapter with EMMO TODOs documented |
| 44 | T44 | thesis chapter: methodology + reflection | 3h | Markdown chapter referencing DEVIATIONS.md |
| 45 | T45 | final demo recording | 60m | 15-min screen capture, end-to-end |

That's the whole project: **45 cards, ~55 hours of focused work, total spend < €25** (well inside the €50 cap).

---

## Part 7 — Audit checklist (run after every task)

Before you say "merge", confirm:

- [ ] Verification command exited 0, output pasted verbatim
- [ ] `git diff --stat` shows only files from the `will-touch` list
- [ ] `git diff -- pixi.toml` is empty (unless the card listed pixi.toml)
- [ ] No new file under `src/palimpsest/` is over 200 LOC (if it is, was it justified?)
- [ ] Commit message follows the `<area>: T##: <summary>` format
- [ ] PROGRESS.md has the new line at the bottom
- [ ] Total LOC has increased by less than 1.5× the increment a senior engineer would estimate (rough sanity check; aim for "shorter than I'd expect")
- [ ] DEVIATIONS.md updated if anything surprising happened

If any box is unchecked, fix before merge.

---

## Part 8 — Drift recovery: what to do when Claude wanders anyway

It will happen. The recovery protocol:

### Severity 1 — minor scope creep (extra helper function, unrequested validation)

> Roll those changes back. Show me `git diff` after. Then commit only the task scope.

Done. ~5 min lost.

### Severity 2 — wrong file edited

> You modified `<file>` which was on the "will NOT touch" list. Run `git checkout -- <file>` and confirm. Then continue with only the task scope.

~10 min lost.

### Severity 3 — Claude went off the rails (added a dep, refactored adjacent code, "improved" things)

> Stop. Run `git reset --hard HEAD` (we have not committed yet). Confirm with `git status` showing clean. Then re-read the task card and restate before doing anything.

~20 min lost.

### Severity 4 — Claude claimed done but verification fails

> Paste the actual verification output. If failing, the task is not done. Do not invent fixes; debug the failure step by step, narrate each step, do not write more code than the smallest possible fix.

~30 min lost.

### Severity 5 — committed bad code

> `git revert <sha>`. Update DEVIATIONS.md with the cause. Re-open the task with a tighter card.

~60 min lost.

**The pattern:** the further Claude has gone, the further you back out. Never try to "patch over" drift — it compounds. Backing out one task is cheap; backing out a week of accumulated drift is fatal.

---

## Part 9 — Anti-patterns Claude Code will try, and the lines that stop them

| Claude says… | Your response |
|---|---|
| "While I'm in here I noticed X could be improved, let me also…" | "Out of scope. Add it as T-backlog and continue with only the task." |
| "I'll add a small helper function for clarity." | "Inline it. No new abstractions in this task." |
| "Let me add tests for the existing function too." | "Out of scope. The card says test only the new function." |
| "I'll use [library not in pixi.toml]." | "Stop. Verify with `pixi run python -c 'import X'`. If it fails, find another way." |
| "The tests pass." | "Paste the verbatim output of the verification command." |
| "I think this should be configurable." | "Hardcode it. No configurability unless the card asks." |
| "I'll add type hints / docstrings / formatting to neighboring code." | "Touch only what the card lists. Neighboring code is out of scope." |
| "I'll create an interface so we can swap implementations later." | "One concrete implementation. We add interfaces on the third use, not the first." |
| "I noticed a bug in unrelated code, let me fix it." | "File it. Don't touch it now." |
| "I'll refactor this for clarity." | "No refactoring unless the card asks." |
| "I'll add error handling for edge cases." | "Only the edge cases the card lists. The rest can crash for now." |
| "Let me also write a README for this module." | "No new docs unless the card asks." |

Print this table. Keep it next to your keyboard for the first two weeks. After that you'll respond automatically.

---

## Part 10 — The daily rhythm (suggestion and not an obligation)

A typical palimpsest workday:

**Morning (20 min):**
- Read last 5 lines of `PROGRESS.md`.
- Read today's first task card.
- Open Claude Code in a fresh conversation.
- Paste the opening prompt with the task code.

**Task block (45–90 min):**
- Claude restates → you confirm or fix the card.
- "Go" → Claude writes code → reports.
- Closing checklist → paste verbatim outputs.
- Audit checklist → all boxes checked.
- Merge → Claude commits + updates `PROGRESS.md`.
- **Close the conversation.**

**Repeat for 2–3 tasks per day.**

**Evening (10 min):**
- Read `PROGRESS.md` to confirm the day's lines.
- If anything surprising happened, append to `DEVIATIONS.md`.
- Glance at tomorrow's first card; sleep on it.

**Sunday (~2 hours):**
- Write next week's task cards in `tasks/`.
- Commit them as `planning: week-N task cards`.
- Update the budget projection in `PROGRESS.md`.

**Friday (~30 min):**
- Run `pixi run palimpsest cost` — confirm under €25 by week 3, under €40 by week 5.
- Run the end-to-end smoke test from week 1: does it still work?
- Commit the week with a tag: `git tag week-N-done`.

---

## Part 11 — When to escalate to a fresh design conversation

Some questions belong with the design assistant, not with Claude Code:

- A task card seems impossible or contradictory → design issue, escalate.
- Two task cards seem to overlap → cards are wrong, escalate.
- A dependency turns out not to work on M1 / on RunPod → design issue, escalate.
- The schema needs a slot type LinkML can't express cleanly → design issue, escalate.
- Spend trajectory is heading over €50 → cost-engineering issue, escalate.
- A thesis-defence question (what would I claim about parser X?) → design discussion, escalate.

For everything that fits in a task card: Claude Code is your only conversation partner. Don't ask the design assistant how to implement T07 — the card already says how.

---

## Part 12 — The meta-reflection (read this after week 1)

After completing week 1, audit yourself:

- Did you write all 8 task cards before starting? If no, **that's the drift root cause** — fix it for week 2.
- Did every task have a verbatim verification command? If you accepted "looks right" anywhere, you'll regret it.
- How many entries are in DEVIATIONS.md? Zero is suspicious (you're missing them); 20 is too many (cards are too loose).
- How much did you spend? Compare to €5 budget for week 1. If much higher, you're over-prompting (re-do, re-do, re-do).
- Is `PROGRESS.md` truthful? Walk the lines, verify each task is actually done.

The first week's audit is the most valuable hour you spend on the whole project.

---

*End of EXECUTION.md.* Save at repo root. Re-read at the start of every week.
