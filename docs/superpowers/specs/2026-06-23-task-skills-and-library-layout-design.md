# Task skills + skill-library layout + visualization/report skills

- **Date:** 2026-06-23
- **Status:** approved design, pre-implementation
- **Supersedes:** T82 (chooses Path B over notebook templates)
- **Extends:** T83 (the `general/` vs `domain/` organization)
- **Records (does not revisit):** T84 (no imported caveman/ponytail skills, no meta self-improvement agent)
- **Maps to:** a future task card (T85) if cards are kept in sync.

## 1. Context

palimpsest has its **own** runtime skill system — distinct from the Claude-Code
build-time skills (caveman, ponytail) that shape the *human's* coding agent.
palimpsest skills are `skills/*/SKILL.md` files: the loader (`src/palimpsest/
skills.py`) parses only YAML frontmatter at boot (~50–100 tokens each) into a
manifest injected into the **agent's** system prompt; the full body is fetched
lazily by the `read_skill` tool only when relevant. Today every skill is
*extraction-shaped*: it declares `targets:` (schema `Measurement` classes it
extracts), gated at load by T69 (`skill_check.py`) — a bogus target quarantines
the skill ("refuse to use, not to boot").

The bodies are **already lazy**, so "fetch when needed instead of loading all"
is the existing design. What is missing: (a) the system can only host
*extraction* skills, so analysis/visualization/reporting cannot be skills; (b)
no organization separating reusable/general skills from per-domain ones.

## 2. Goals

1. Generalize the skill system to host **non-extraction "task" skills** (Path B)
   under the same loader, manifest, and `check_skill` machinery.
2. Reorganize `skills/` into `skills/domain/` (extraction) and `skills/general/`
   (task), with a manifest grouped by kind.
3. Ship two task skills: `notebook-analysis` (marimo) and `report-writing`
   (self-contained HTML), each producing an artifact over the extracted RDF graph
   with provenance carried through.
4. Keep constrained autonomy **enforced in code** for task skills too: their
   declared `reads:` (schema classes) and `uses:` (tools) are gated at load.

## 3. Non-goals (recorded decisions)

- No imported caveman/ponytail/meta skills (T84): those govern the build-time
  agent, not palimpsest's runtime; a self-improvement loop is a planner/critic
  anti-pattern + autonomous spend + self-edit outside the workspace fence.
- No new agent tool: task skills compose existing `sparql_query` / `write_file`
  / `open_notebook`.
- No topic-gated manifest now (deferred until ~15+ skills): the manifest is
  built once at system-prompt time, before any paper (hence its topic) is known,
  so topic-filtering is both premature and architecturally awkward. Grouping by
  kind is the cheap win.

## 4. Design

### 4.0 Prerequisite — decouple `extract.py` from the path convention (the B1 fix)

`src/palimpsest/tools/extract.py:632` reconstructs `Path("skills") / skill_name`
**independently of the loader's glob**. Moving skills would silently break this:
`normalize.py` returns `{}` for a missing `normalization.yaml`, so the per-skill
normalization overlay would **vanish from every extraction prompt with no
error**. This MUST be fixed *before* any move.

- Add `SkillLoader.skill_dir(name) -> Path` returning `self._skills[name]
  ["path"].parent` (raises `KeyError` for unknown/quarantined names, like
  `load()`).
- Rewrite `extract.py` to `build_normalization_prompt([_LOADER.skill_dir(skill_name)])`
  instead of reconstructing the path. After this, skills are location-agnostic.
- Regression test: the normalization overlay text is present in the built prompt
  for a skill whose directory is **not** at `skills/<name>` (e.g. parametrize the
  loader root, or assert after the move).

### 4.1 Skill kinds — the `kind:` field

One new frontmatter field: `kind: extraction | task`. **Absent → `extraction`**,
so the two existing skills need no edits. `kind` in frontmatter is the source of
truth, **not** the folder — paths move, the contract should not. Frontmatter
already tolerates unknown keys (`ontology: h2kg` is one today), so adding `kind`
is inert for current code.

### 4.2 Folder layout & discovery

```
skills/
  domain/   oer-extraction/   pemwe-anode/        (kind: extraction)
  general/  notebook-analysis/  report-writing/   (kind: task)
```

Loader glob `skills/*/SKILL.md` → `skills/**/SKILL.md` (recursive). Verified: no
stray `SKILL.md` under any `references/`; `skills.py:67` is the only walker of
`skills/`. Existing skills move via `git mv` (safe after §4.0). Update the 4 test
path constructors (`tests/test_normalize.py:24,130`,
`tests/test_skill_check.py:80,106`) and docs referencing the old layout
(EXECUTION.md, PROGRESS.md, T20/21/69/71 cards — non-executed, but kept accurate).

### 4.3 The gate (task skills)

Task skills declare, instead of `targets:`:

```yaml
kind: task
reads: [Overpotential, TafelSlope, Evidence, Paper]   # schema class names its SPARQL touches
uses:  [sparql_query, write_file, open_notebook]      # tool names it calls
```

- **`reads:`** validated against **all** schema classes (new `all_classes()` in
  `skill_check.py` = every key under `classes:`, not just `measurement_classes()`
  — a notebook reads `Evidence`/`Paper` for provenance). Hard check at
  `SkillLoader.__init__` (mirrors `check_targets`): a bogus class → quarantine.
- **`uses:`** validated against the `TOOLS` registry. **Cannot run at
  `__init__`** — `_LOADER = SkillLoader()` is constructed during the
  `read_skill` import (`tools/__init__.py:32`), *before* `open_notebook` /
  `sparql_query` / `write_file` register (lines 35–41), so `TOOLS` is
  incomplete. Evaluate it **lazily, once**, via a memoized `_ensure_finalized()`
  guard called at the top of **every** accessor — `manifest()`, `names()`,
  `load()`, `skill_dir()` — that moves `uses:` failures into `self.invalid`.
  Safe because no accessor is called at import time (verified), so on first
  runtime call `TOOLS` is complete. Memoization (a `self._finalized` flag)
  prevents re-validating on every `manifest()` rebuild.

`check_skill` / `validate_skill` / `render_report` extend to report
`reads:`/`uses:` PASS/FAIL for task skills (replacing the stale
"(declares no targets:)" line for `kind: task`). This lets the agent
self-verify a skill it just authored — the constrained-self-extension evidence.

### 4.4 The two task skills

Each ships a vetted reference skeleton in its `references/` folder (reusing the
existing convention) so the agent **adapts** known-good code rather than
generating from scratch — cheaper and more reliable, still a skill.

**`skills/general/notebook-analysis/`** — `reads: [Overpotential, TafelSlope,
Stability, Evidence, Paper]`, `uses: [sparql_query, write_file, open_notebook]`.
Body teaches: SPARQL the store → SPARQL result rows (plain Python lists, **no
dataframe dep**) → overpotential histogram + Tafel scatter + parser-coverage
table via `plotly.graph_objects`, **every cell carrying provenance columns**
(paper_hash, parser, page) so the human verifies. Adapt
`references/notebook_template.py`; change only the SPARQL + store path. Spawn via
`open_notebook` (never auto-run).

**`skills/general/report-writing/`** — `reads: [Overpotential, TafelSlope,
MassActivity, Stability, Evidence, Paper]`, `uses: [sparql_query, write_file]`.
Body teaches: a self-contained **HTML** report — SPARQL-backed figures +
embedded `plotly.graph_objects` charts (via `fig.to_html()`, **no kaleido**) + a
**provenance table** + the domain caveats (pulled from the extraction skills'
"common traps": never fuse RDE and PEMWE stability). Written to
`workspace/reports/`. Same do-not-fabricate discipline as extraction.

### 4.5 Manifest grouping

`manifest()` emits two sections (`## Domain skills`, `## General skills`) via an
explicit two-pass over `self._skills` by `kind` (the loader preserves discovery
order today, so grouping is net-new logic). One line per skill unchanged. This
changes the static system-prompt prefix exactly once at deploy (a one-time prompt-
cache bust, not mid-session churn — acceptable, noted per CLAUDE.md).

## 5. Invariants preserved (verified by review)

- **Workspace confinement:** `write_file`/`open_notebook` route through
  `policy.assert_writable`; task skills add no new write path.
- **Provenance / read-only graph:** `sparql_query` → pyoxigraph `query()` is
  read-only; an INSERT raises. No un-provenanced-triple path.
- **Budget:** task skills add no new tool, so no new spend surface; any paid
  call stays metered.
- **No auto-execute:** marimo is spawned via `marimo edit`, never `run`.

## 6. Build sequence

1. **Decouple** `extract.py` from the path convention (`skill_dir`) + regression
   test. ← de-risks everything; lands first.
2. **Gate**: `kind`/`reads`/`uses` parsing, `all_classes()`, lazy memoized
   `_ensure_finalized()`, extended `validate_skill`/`render_report`.
3. **Move**: `git mv` skills → `domain/`, glob → `**`, update test paths + docs.
4. **Skills**: add `skills/general/{notebook-analysis,report-writing}/` with
   reference skeletons.
5. **Manifest**: grouped output.

## 7. Verification

- Existing skill/normalize/agent tests stay green (skill names unchanged, so
  manifest/prompt assertions survive the move).
- New: normalization overlay present for a **relocated** skill dir (guards B1).
- New: a task skill with a bogus `uses:` is quarantined when reached via
  `load()`/`names()` **without** calling `manifest()` first (guards B2).
- New: `reads:` accepts a non-Measurement class (`Evidence`) and quarantines a
  bogus class.
- New: a clean task skill loads and `check_skill` PASSes, reporting reads/uses.
- `python -c "import ast; ast.parse(open(skeleton).read())"` on each reference
  skeleton.
- Spend €0 (no LLM/GPU; read-only over the existing store).

## 8. Files

**Touch:** `src/palimpsest/skills.py` (glob, `kind`/`reads`/`uses`, lazy
`_ensure_finalized`, `skill_dir`), `src/palimpsest/skill_check.py`
(`all_classes`, extend `validate_skill`/`render_report`),
`src/palimpsest/tools/check_skill.py` (task reporting),
`src/palimpsest/tools/extract.py` (`skill_dir` decouple),
`src/palimpsest/agent.py` (grouped manifest), `git mv` the 2 skills, new
`skills/general/{notebook-analysis,report-writing}/{SKILL.md,references/}`, test
path + doc updates.

**Do not touch:** the extraction-`targets:` gate semantics, the
pipeline/provenance path, the budget machinery, `policy.py`.

## 9. Open risks / notes

- `render_report` empty-`checks` branch (`skill_check.py:171`) must special-case
  `kind: task` or it prints a misleading "no targets" line (N1).
- `skills.py:8-15` frontmatter docstring is already stale (omits `ontology:`);
  update it alongside `kind:`, don't cite it as authoritative.
- Manifest grouping requires sorting/second pass — not free; small but net-new.
- **Dependencies:** the reference skeletons use only `marimo` + `plotly` (both
  in `pixi.toml`). `plotly.graph_objects` is mandatory (not `plotly.express`,
  which pulls `pandas`); no `polars`/`pandas`/`matplotlib`. Static PNG/SVG export
  (markdown report) needs `kaleido` — **not** in `pixi.toml`; deferred behind a
  confirm-before-adding decision, so the report ships as HTML for now.
