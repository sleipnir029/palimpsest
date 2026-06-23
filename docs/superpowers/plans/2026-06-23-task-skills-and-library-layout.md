# Task Skills + Skill-Library Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize palimpsest's skill system to host non-extraction "task" skills (notebook-analysis, report-writing) under the same loader/gate, organized into `general/` and `domain/` folders, with constrained-autonomy gating extended to task skills.

**Architecture:** Add a `kind:` frontmatter field (default `extraction`). Task skills declare `reads:` (schema classes, hard-gated at load against all schema classes) and `uses:` (tool names, lazily gated against the `TOOLS` registry on first loader access — because the loader is constructed before most tools register). Decouple `extract.py` from the `skills/<name>` path convention first, so skills can be relocated safely. Then `git mv` the two extraction skills into `skills/domain/`, add two `skills/general/` task skills with vetted reference skeletons, and group the system-prompt manifest by kind.

**Tech Stack:** Python 3.11, pixi, PyYAML, pyoxigraph, marimo, plotly (graph_objects), pytest.

## Global Constraints

- Python 3.11; dependencies via pixi only. **No new dependency** without explicit confirm (CLAUDE.md).
- Reference skeletons use **only `marimo` + `plotly`** (both already in `pixi.toml`). Use `plotly.graph_objects` — **not** `plotly.express` (pulls `pandas`). No `polars`/`pandas`/`matplotlib`/`kaleido`.
- This work spends **€0**: no LLM/GPU calls; read-only over the existing store; tests only `ast.parse` generated skeletons, never run them against a populated store.
- Invariants untouched: workspace confinement (`policy.py`), provenance-on-insert, the €50 budget gate. Task skills add **no new tool**.
- `kind:` in frontmatter is the source of truth for skill kind, **not** the folder. Absent → `extraction`.
- Commit directly to `main` (no feature branch — user's standing rule). Every commit message ends with the trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Run tests with `pixi run pytest <args>` (the repo's pixi env; `pixi.toml` also defines `pixi run test` = `pytest -v` for the whole suite). Focused after each task, e.g. `pixi run pytest tests/test_skills.py tests/test_skill_check.py tests/test_normalize.py -q`.

---

### Task 1: Decouple `extract.py` from the path convention (`skill_dir`) + recursive glob

**Why first:** `extract.py:632` reconstructs `Path("skills") / skill_name` independently of the loader. Moving skills later would silently drop the per-skill normalization overlay (`normalize.py` returns `{}` for a missing file — no error). Fixing this *first* makes every later step safe. The `**` glob is backward-compatible (still finds depth-1 skills), so this task changes behavior for nobody yet.

**Files:**
- Modify: `src/palimpsest/skills.py` (add `skill_dir`; glob `*/SKILL.md` → `**/SKILL.md`)
- Modify: `src/palimpsest/tools/extract.py:632`
- Test: `tests/test_skills.py` (new `skill_dir` + relocation tests)

**Interfaces:**
- Produces: `SkillLoader.skill_dir(name: str) -> pathlib.Path` — the directory containing the named skill's `SKILL.md`; raises `KeyError` for unknown/quarantined names (same contract as `load`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_skills.py`:

```python
from pathlib import Path

import yaml

from palimpsest.normalize import build_normalization_prompt


def _write_min_skill(root, name, *, normalization=None):
    """Materialize <root>/<...>/<name>/SKILL.md (+ optional normalization.yaml)."""
    d = root / name
    d.mkdir(parents=True)
    fm = {"name": name, "description": "t", "when_to_use": "t", "version": "1.0.0"}
    body = "# body\n\n" + ("filler. " * 200)
    (d / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + body, encoding="utf-8"
    )
    if normalization is not None:
        (d / "normalization.yaml").write_text(yaml.safe_dump(normalization), encoding="utf-8")
    return d


def test_skill_dir_returns_containing_directory():
    loader = SkillLoader()
    p = loader.skill_dir("oer-extraction")
    assert p.is_dir()
    assert (p / "SKILL.md").exists()


def test_skill_dir_unknown_raises_keyerror():
    loader = SkillLoader()
    with pytest.raises(KeyError):
        loader.skill_dir("does-not-exist")


def test_loader_finds_skills_nested_two_levels(tmp_path):
    """Recursive glob discovers a skill nested under an extra folder (the future
    skills/domain/ and skills/general/ layout)."""
    _write_min_skill(tmp_path / "domain", "nested-skill")
    loader = SkillLoader(root=tmp_path)
    assert "nested-skill" in loader.names()


def test_normalization_overlay_survives_relocation(tmp_path):
    """B1 guard: skill_dir points at the real (possibly relocated) directory, so
    the normalization overlay is found regardless of nesting depth."""
    _write_min_skill(
        tmp_path / "domain", "relocated",
        normalization={"domain": "relocated", "active_metals": ["Ir"]},
    )
    loader = SkillLoader(root=tmp_path)
    block = build_normalization_prompt([loader.skill_dir("relocated")])
    assert "relocated" in block  # overlay was loaded, not silently {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest tests/test_skills.py -q`
Expected: FAIL — `AttributeError: 'SkillLoader' object has no attribute 'skill_dir'` (and the nested-discovery test fails because the one-level glob misses `domain/nested-skill`).

- [ ] **Step 3: Change the glob and add `skill_dir`**

In `src/palimpsest/skills.py`, change the discovery glob in `__init__`:

```python
        for skill_md in sorted(self.root.glob("**/SKILL.md")):
```

Add this method to `SkillLoader` (after `load`):

```python
    def skill_dir(self, name: str) -> Path:
        """Directory containing the named skill's SKILL.md (for normalization etc.).

        Source of truth for a skill's on-disk location, so callers never
        reconstruct `Path("skills") / name` (which breaks when skills move).
        """
        if name not in self._skills:
            raise KeyError(name)
        return self._skills[name]["path"].parent
```

- [ ] **Step 4: Rewrite the extract.py path construction**

In `src/palimpsest/tools/extract.py`, change line 632 from:

```python
    norm = build_normalization_prompt([Path("skills") / skill_name])
```

to:

```python
    norm = build_normalization_prompt([_LOADER.skill_dir(skill_name)])
```

(`_LOADER` is already imported and used in this file — see lines 628/630. The unused `Path` import stays if other code uses it; if `Path` is now unused, leave it — a separate concern, do not chase it here.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pixi run pytest tests/test_skills.py tests/test_normalize.py -q`
Expected: PASS (all, including the existing manifest/load tests).

- [ ] **Step 6: Commit**

```bash
git add src/palimpsest/skills.py src/palimpsest/tools/extract.py tests/test_skills.py
git commit -m "refactor(skills): add skill_dir + recursive glob; decouple extract.py from path convention"
```

---

### Task 2: `kind`/`reads` load-gate (`all_classes` + hard quarantine at __init__)

**Files:**
- Modify: `src/palimpsest/skill_check.py` (add `all_classes`, `check_reads`)
- Modify: `src/palimpsest/skills.py` (parse `kind`/`reads`; gate task skills; store `kind`)
- Test: `tests/test_skill_check.py`

**Interfaces:**
- Consumes: `SkillLoader(root=...)`, `loader.names()`, `loader.invalid` (existing).
- Produces: `skill_check.all_classes() -> set[str]` (every key under `classes:` in the schema); `skill_check.check_reads(skill_name: str, reads: list[str]) -> list[str]` (the reads not in `all_classes()`). `SkillLoader._skills[name]` gains a `"kind"` entry (`"extraction"` | `"task"`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_skill_check.py`. First a task-skill writer helper:

```python
def _write_task_skill(root, name, *, reads=None, uses=None):
    """Materialize a minimal kind:task SKILL.md."""
    d = root / name
    d.mkdir(parents=True)
    fm = {"name": name, "description": "t", "when_to_use": "t",
          "version": "1.0.0", "kind": "task"}
    if reads is not None:
        fm["reads"] = reads
    if uses is not None:
        fm["uses"] = uses
    body = "# body\n\n" + ("filler. " * 60)
    (d / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + body, encoding="utf-8"
    )
    return d
```

Then the tests:

```python
def test_all_classes_includes_non_measurement_classes():
    from palimpsest.skill_check import all_classes
    ac = all_classes()
    for name in ["Evidence", "Paper", "Condition", "Overpotential"]:
        assert name in ac, f"{name} should be a schema class"


def test_check_reads_against_all_classes():
    from palimpsest.skill_check import check_reads
    assert check_reads("x", ["Overpotential", "Evidence", "Paper"]) == []
    assert check_reads("x", ["Overpotential", "NoSuchClass"]) == ["NoSuchClass"]


def test_task_skill_with_valid_reads_loads(tmp_path):
    _write_task_skill(tmp_path / "general", "good-task",
                      reads=["Overpotential", "Evidence"], uses=["sparql_query"])
    loader = SkillLoader(root=tmp_path)
    assert "good-task" in loader.names()
    assert "good-task" not in loader.invalid


def test_task_skill_with_bad_reads_is_quarantined(tmp_path):
    _write_task_skill(tmp_path / "general", "bad-reads",
                      reads=["Overpotential", "NoSuchClass"], uses=["sparql_query"])
    with pytest.warns(UserWarning, match="NoSuchClass"):
        loader = SkillLoader(root=tmp_path)
    assert "bad-reads" not in loader.names()
    assert "bad-reads" in loader.invalid
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest tests/test_skill_check.py -q -k "all_classes or check_reads or task_skill"`
Expected: FAIL — `ImportError: cannot import name 'all_classes'` / the bad-reads skill is NOT quarantined yet (loader ignores `reads:`).

- [ ] **Step 3: Add `all_classes` + `check_reads` to skill_check.py**

After `check_targets` in `src/palimpsest/skill_check.py`:

```python
@cache
def all_classes() -> set[str]:
    """Every class name declared under `classes:` in the schema.

    Broader than `measurement_classes()` — a task skill's `reads:` may name
    Evidence/Paper/Condition for provenance, not just Measurement subclasses.
    """
    return set((_schema_doc().get("classes") or {}).keys())


def check_reads(skill_name: str, reads: list[str]) -> list[str]:
    """Offline membership check: reads that are not any schema class."""
    ac = all_classes()
    return [r for r in reads if r not in ac]
```

- [ ] **Step 4: Gate task skills in the loader**

In `src/palimpsest/skills.py`, update the import and the `__init__` loop body. Change the import:

```python
from .skill_check import check_reads, check_targets
```

Replace the per-skill body of the `for skill_md in ...` loop with:

```python
            meta, _ = _split(skill_md.read_text(encoding="utf-8"))
            name = meta["name"]
            self._meta[name] = meta
            kind = meta.get("kind", "extraction")
            if kind == "task":
                reads = meta.get("reads") or []
                missing = check_reads(name, reads)
                if missing:
                    reason = f"reads unknown schema classes: {', '.join(missing)}"
                    self.invalid[name] = reason
                    warnings.warn(f"skill {name!r} quarantined: {reason}", stacklevel=2)
                    continue
            else:
                targets = meta.get("targets")
                if targets:
                    missing = check_targets(name, targets)
                    if missing:
                        reason = f"targets unknown schema classes: {', '.join(missing)}"
                        self.invalid[name] = reason
                        warnings.warn(f"skill {name!r} quarantined: {reason}", stacklevel=2)
                        continue
            self._skills[name] = {"path": skill_md, "meta": meta, "kind": kind}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pixi run pytest tests/test_skill_check.py tests/test_skills.py -q`
Expected: PASS (existing extraction quarantine tests unaffected; new task-reads tests pass).

- [ ] **Step 6: Commit**

```bash
git add src/palimpsest/skill_check.py src/palimpsest/skills.py tests/test_skill_check.py
git commit -m "feat(skills): kind:task + reads: load-gate against all schema classes"
```

---

### Task 3: Lazy memoized `uses:` gate across all accessors (B2 fix)

**Why lazy:** `_LOADER = SkillLoader()` is constructed during the `read_skill` import (`tools/__init__.py:32`), before `open_notebook`/`sparql_query`/`write_file` register (lines 35–41). Checking `uses:` against `TOOLS` at `__init__` would falsely quarantine. No accessor runs at import time (verified), so deferring the `uses:` check to the first accessor call — when `TOOLS` is complete — is safe. It must run on **every** accessor (`manifest`/`names`/`load`/`skill_dir`), memoized, because `load()`/`names()` are reachable without `manifest()`.

**Files:**
- Modify: `src/palimpsest/skills.py` (`_finalized` flag, `_ensure_finalized`, guard all accessors)
- Test: `tests/test_skill_check.py`

**Interfaces:**
- Produces: `SkillLoader._ensure_finalized() -> None` (idempotent; on first call, quarantines task skills whose `uses:` names an unregistered tool). All public accessors call it first.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_skill_check.py` (uses the `_write_task_skill` helper from Task 2):

```python
def test_task_skill_with_bad_uses_quarantined_via_names(tmp_path):
    """B2 guard: the uses-gate fires when reached through names(), WITHOUT
    manifest() ever being called."""
    _write_task_skill(tmp_path / "general", "bad-uses",
                      reads=["Overpotential"], uses=["sparql_query", "no_such_tool"])
    loader = SkillLoader(root=tmp_path)  # not yet finalized — no warning here
    with pytest.warns(UserWarning, match="no_such_tool"):
        names = loader.names()
    assert "bad-uses" not in names
    assert "bad-uses" in loader.invalid


def test_task_skill_with_bad_uses_quarantined_via_load(tmp_path):
    _write_task_skill(tmp_path / "general", "bad-uses2",
                      reads=["Overpotential"], uses=["definitely_not_a_tool"])
    loader = SkillLoader(root=tmp_path)
    with pytest.warns(UserWarning, match="definitely_not_a_tool"):
        with pytest.raises(KeyError):
            loader.load("bad-uses2")
    assert "bad-uses2" in loader.invalid


def test_task_skill_with_valid_uses_survives_finalize(tmp_path):
    _write_task_skill(tmp_path / "general", "ok-task",
                      reads=["Overpotential"], uses=["sparql_query", "write_file"])
    loader = SkillLoader(root=tmp_path)
    assert "ok-task" in loader.names()
    assert "ok-task" not in loader.invalid
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest tests/test_skill_check.py -q -k "bad_uses or valid_uses"`
Expected: FAIL — bad-`uses` skills are NOT quarantined (no `uses:` gate exists yet); the skills remain in `names()`/loadable.

- [ ] **Step 3: Implement `_ensure_finalized` and guard accessors**

In `src/palimpsest/skills.py`, set the flag in `__init__` (after `self.invalid = {}`):

```python
        self._finalized = False
```

Add the method (after `__init__`, before `manifest`):

```python
    def _ensure_finalized(self) -> None:
        """Run the deferred `uses:` gate once, when the tool registry is complete.

        The loader is constructed during early tool import (before most tools
        register), so a task skill's `uses:` cannot be checked at __init__.
        Every accessor calls this first; it runs at most once.
        """
        if self._finalized:
            return
        self._finalized = True
        from .tools import TOOLS  # lazy: avoid the import cycle; complete at runtime
        for name in list(self._skills):
            if self._skills[name]["kind"] != "task":
                continue
            uses = self._skills[name]["meta"].get("uses") or []
            missing = [u for u in uses if u not in TOOLS]
            if missing:
                reason = f"uses unregistered tools: {', '.join(missing)}"
                self.invalid[name] = reason
                warnings.warn(f"skill {name!r} quarantined: {reason}", stacklevel=2)
                del self._skills[name]
```

Add `self._ensure_finalized()` as the first line of `manifest`, `names`, `load`, and `skill_dir`. For example, `names` becomes:

```python
    def names(self) -> list[str]:
        """Sorted list of registered skill names — for error messages and discovery."""
        self._ensure_finalized()
        return sorted(self._skills)
```

Do the same (first line `self._ensure_finalized()`) in `manifest`, `load`, and `skill_dir`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run pytest tests/test_skill_check.py tests/test_skills.py -q`
Expected: PASS (the bad-`uses` skills are now quarantined on first access; valid ones survive; all existing tests green).

- [ ] **Step 5: Commit**

```bash
git add src/palimpsest/skills.py tests/test_skill_check.py
git commit -m "feat(skills): lazy memoized uses: gate across all loader accessors"
```

---

### Task 4: Extend `check_skill`/`validate_skill`/`render_report` for task skills

**Files:**
- Modify: `src/palimpsest/skill_check.py` (`ToolCheck`, `SkillReport.tool_checks`/`kind`, kind-aware `validate_skill`, `render_report`)
- Test: `tests/test_skill_check.py`

**Interfaces:**
- Consumes: `loader._meta[name]` carrying `kind`/`reads`/`uses` (from Tasks 2–3).
- Produces: `SkillReport` gains `tool_checks: list[ToolCheck]` and `kind: str`; `validate_skill` reports `reads:` membership + `uses:` registry-existence for `kind: task`; `render_report` prints both and `ok` accounts for unregistered tools.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_skill_check.py`:

```python
def test_validate_task_skill_reports_reads_and_uses(tmp_path):
    _write_task_skill(tmp_path / "general", "good-task",
                      reads=["Overpotential", "Evidence"], uses=["sparql_query"])
    loader = SkillLoader(root=tmp_path)
    report = validate_skill("good-task", loader, resolve_iris=False)
    assert report.kind == "task"
    assert report.missing_classes == []
    assert [t.name for t in report.tool_checks] == ["sparql_query"]
    assert all(t.registered for t in report.tool_checks)
    assert report.ok
    rendered = render_report(report)
    assert "PASS" in rendered
    assert "sparql_query" in rendered
    assert "no targets" not in rendered.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest tests/test_skill_check.py -q -k validate_task_skill`
Expected: FAIL — `AttributeError: 'SkillReport' object has no attribute 'kind'` (or `tool_checks`).

- [ ] **Step 3: Extend the dataclasses and `validate_skill`**

In `src/palimpsest/skill_check.py`, add after `ClassCheck`:

```python
@dataclass
class ToolCheck:
    name: str
    registered: bool
```

Extend `SkillReport` with two fields (keep existing fields):

```python
@dataclass
class SkillReport:
    skill: str
    checks: list[ClassCheck]
    iris_resolved: bool
    tool_checks: list["ToolCheck"] = field(default_factory=list)
    kind: str = "extraction"
```

Update the `ok` property to account for tools:

```python
    @property
    def ok(self) -> bool:
        return (
            not self.missing_classes
            and not self.unresolved_iris
            and all(t.registered for t in self.tool_checks)
        )
```

Add a `kind: task` branch at the **top** of `validate_skill` (right after the `meta is None` guard):

```python
    kind = meta.get("kind", "extraction")
    if kind == "task":
        ac = all_classes()
        checks = [ClassCheck(name=r, in_schema=(r in ac)) for r in (meta.get("reads") or [])]
        from .tools import TOOLS  # lazy: registry complete at runtime
        tool_checks = [ToolCheck(name=u, registered=(u in TOOLS)) for u in (meta.get("uses") or [])]
        return SkillReport(
            skill=name, checks=checks, iris_resolved=resolve_iris,
            tool_checks=tool_checks, kind=kind,
        )
```

(The existing `targets:` logic below is unchanged; add `kind=kind` to its returned `SkillReport(...)` too so extraction reports carry the field.)

- [ ] **Step 4: Update `render_report`**

In `render_report`, after the per-class loop and before the `if not report.checks:` line, add the tool lines:

```python
    for t in report.tool_checks:
        if t.registered:
            lines.append(f"  ✓ tool {t.name}: registered")
        else:
            lines.append(f"  ✗ tool {t.name}: NOT in tool registry")
```

Replace the empty-checks branch so it is kind-aware:

```python
    if not report.checks:
        what = "reads:" if report.kind == "task" else "targets:"
        lines.append(f"  (skill declares no {what})")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pixi run pytest tests/test_skill_check.py -q`
Expected: PASS (new task-report test passes; existing extraction reports unchanged — `tool_checks` empty so `ok` is unaffected).

- [ ] **Step 6: Commit**

```bash
git add src/palimpsest/skill_check.py tests/test_skill_check.py
git commit -m "feat(skills): check_skill reports reads:/uses: for task skills"
```

---

### Task 5: Group the manifest by kind

**Files:**
- Modify: `src/palimpsest/skills.py` (`manifest`)
- Test: `tests/test_skills.py`

**Interfaces:**
- Produces: `manifest()` returns a string with a `**Domain skills**` section and/or a `**General skills**` section (a section is omitted when empty). One line per skill, `- name: description`, unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_skills.py` (reuses `_write_min_skill` + a task writer; inline a small task writer here):

```python
def _write_task(root, name):
    d = root / name
    d.mkdir(parents=True)
    fm = {"name": name, "description": "task skill", "when_to_use": "t",
          "version": "1.0.0", "kind": "task",
          "reads": ["Overpotential"], "uses": ["sparql_query"]}
    body = "# body\n\n" + ("filler. " * 60)
    (d / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + body, encoding="utf-8"
    )


def test_manifest_groups_domain_and_general(tmp_path):
    _write_min_skill(tmp_path / "domain", "an-extraction")  # kind defaults to extraction
    _write_task(tmp_path / "general", "a-task")
    loader = SkillLoader(root=tmp_path)
    m = loader.manifest()
    assert "**Domain skills**" in m
    assert "**General skills**" in m
    assert "an-extraction" in m and "a-task" in m
    # domain section precedes general section
    assert m.index("**Domain skills**") < m.index("**General skills**")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run pytest tests/test_skills.py -q -k manifest_groups`
Expected: FAIL — no `**Domain skills**` header (manifest is a flat list today).

- [ ] **Step 3: Implement grouped manifest**

Replace `SkillLoader.manifest` in `src/palimpsest/skills.py` with:

```python
    def manifest(self) -> str:
        """One-line-per-skill listing for the system prompt, grouped by kind."""
        self._ensure_finalized()
        domain = [s for s in self._skills.values() if s["kind"] != "task"]
        task = [s for s in self._skills.values() if s["kind"] == "task"]

        def _lines(group):
            return [f"- {s['meta']['name']}: {s['meta']['description']}" for s in group]

        out: list[str] = []
        if domain:
            out.append("**Domain skills** (extraction — load before extracting in that domain):")
            out += _lines(domain)
        if task:
            if out:
                out.append("")
            out.append("**General skills** (analysis/reporting tasks):")
            out += _lines(task)
        return "\n".join(out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run pytest tests/test_skills.py tests/test_agent_tools.py -q`
Expected: PASS (`test_manifest_lists_oer_extraction` still passes — the substring is present; the agent-prompt test still sees `oer-extraction`).

- [ ] **Step 5: Commit**

```bash
git add src/palimpsest/skills.py tests/test_skills.py
git commit -m "feat(skills): group system-prompt manifest by kind (domain/general)"
```

---

### Task 6: Move the two extraction skills into `skills/domain/`

**Why now:** All loader/gate/manifest logic is built and tested on the current layout. The `**` glob (Task 1) already discovers nested skills, so this task is a pure relocation plus updating hard-coded path strings in two test files.

**Files:**
- Move: `skills/oer-extraction/` → `skills/domain/oer-extraction/`; `skills/pemwe-anode/` → `skills/domain/pemwe-anode/`
- Modify: `tests/test_normalize.py:24,130`; `tests/test_skill_check.py:80,106`
- Modify: `src/palimpsest/skills.py` docstring (loader header) to note the `general/`+`domain/` layout and `kind:`/`reads:`/`uses:` frontmatter
- Modify: living docs that name the old path — `EXECUTION.md`, `PROGRESS.md` (leave historical task cards T20/T21/T69/T71 as-is; they record past state)

- [ ] **Step 1: Move the skill folders**

```bash
git mv skills/oer-extraction skills/domain/oer-extraction
git mv skills/pemwe-anode skills/domain/pemwe-anode
```

- [ ] **Step 2: Run the suite to see exactly what breaks**

Run: `pixi run pytest tests/test_normalize.py tests/test_skill_check.py -q`
Expected: FAIL in `tests/test_normalize.py` (the `OER_DIR` constant and the `build_normalization_prompt([Path("skills")/...])` call now point at non-existent dirs) and `tests/test_skill_check.py` (the two `Path("skills/<name>/SKILL.md")` reads). This confirms the blast radius is exactly these four sites.

- [ ] **Step 3: Update the hard-coded test paths**

`tests/test_normalize.py:24`:

```python
OER_DIR = Path(__file__).parent.parent / "skills" / "domain" / "oer-extraction"
```

`tests/test_normalize.py:130` (inside `test_pemwe_overlay_does_not_shadow_universal_keys`):

```python
    prompt = build_normalization_prompt(
        [Path("skills") / "domain" / "oer-extraction",
         Path("skills") / "domain" / "pemwe-anode"]
    )
```

`tests/test_skill_check.py:80`:

```python
        Path("skills/domain/oer-extraction/SKILL.md").read_text(encoding="utf-8")
```

`tests/test_skill_check.py:106`:

```python
        Path("skills/domain/pemwe-anode/SKILL.md").read_text(encoding="utf-8")
```

- [ ] **Step 4: Update the loader docstring + living docs**

In `src/palimpsest/skills.py`, update the module docstring header (lines ~1–18) to describe the current reality: skills live under `skills/domain/` (extraction) and `skills/general/` (task); frontmatter carries `kind:` (default `extraction`), and task skills declare `reads:`/`uses:` instead of `targets:`. Replace the stale single-skill example accordingly. Then grep and fix living docs:

```bash
grep -rn "skills/oer-extraction\|skills/pemwe-anode" EXECUTION.md PROGRESS.md 2>/dev/null
```

Update each hit in `EXECUTION.md`/`PROGRESS.md` to the `skills/domain/...` path. Do **not** edit `tasks/T20*`, `T21*`, `T69*`, `T71*` — they are historical records.

- [ ] **Step 5: Run the full suite to verify green**

Run: `pixi run pytest tests/test_skills.py tests/test_skill_check.py tests/test_normalize.py tests/test_agent_tools.py -q`
Expected: PASS (skill names unchanged → manifest/prompt assertions survive; paths now resolve).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(skills): relocate extraction skills to skills/domain/"
```

---

### Task 7: Add the two `skills/general/` task skills with reference skeletons

**Files:**
- Create: `skills/general/notebook-analysis/SKILL.md`
- Create: `skills/general/notebook-analysis/references/notebook_template.py`
- Create: `skills/general/report-writing/SKILL.md`
- Create: `skills/general/report-writing/references/report_template.py`
- Test: `tests/test_general_skills.py` (new)

**Interfaces:**
- Consumes: the loader/gate from Tasks 1–5 (these skills must pass the `reads:`/`uses:` gate, so every declared class and tool must be real).
- Produces: two registered task skills discoverable via `manifest()` and `read_skill`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_general_skills.py`:

```python
"""The two general/ task skills load, pass the gate, and ship parseable skeletons."""

from __future__ import annotations

import ast
from pathlib import Path

from palimpsest.skill_check import render_report, validate_skill
from palimpsest.skills import SkillLoader


def test_general_skills_registered_not_quarantined():
    loader = SkillLoader()
    names = loader.names()
    for n in ("notebook-analysis", "report-writing"):
        assert n in names, f"{n} should be registered"
        assert n not in loader.invalid


def test_general_skills_check_skill_passes():
    loader = SkillLoader()
    for n in ("notebook-analysis", "report-writing"):
        report = validate_skill(n, loader, resolve_iris=False)
        assert report.kind == "task"
        assert report.ok, render_report(report)


def test_reference_skeletons_parse():
    for p in (
        "skills/general/notebook-analysis/references/notebook_template.py",
        "skills/general/report-writing/references/report_template.py",
    ):
        ast.parse(Path(p).read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest tests/test_general_skills.py -q`
Expected: FAIL — the skills do not exist (`notebook-analysis` not in `names()`; skeleton files missing).

- [ ] **Step 3: Create the notebook-analysis skill**

`skills/general/notebook-analysis/SKILL.md`:

```markdown
---
name: notebook-analysis
description: Build an interactive marimo notebook that queries the extracted RDF graph and visualizes OER metrics (overpotential distribution, Tafel comparison, parser coverage), with provenance carried into every cell. Use when the researcher wants to explore the graph interactively.
when_to_use: user asks to analyze, explore, plot, or visualize the extracted graph interactively
version: 1.0.0
kind: task
reads:
  - Overpotential
  - TafelSlope
  - Stability
  - Evidence
  - Paper
uses:
  - sparql_query
  - write_file
  - open_notebook
---

# Notebook analysis playbook

Build a **marimo** notebook over the extracted graph. Never auto-run it — write
it with `write_file` into `workspace/notebooks/`, then spawn it with
`open_notebook` so the human drives it.

## Discipline
- Start from `references/notebook_template.py`; change only the SPARQL query and
  the store path. Keep it minimal — one figure per question.
- Query the store directly inside the notebook via `palimpsest.store.RDFStore`.
  Use `sparql_query` first to preview a query before baking it in.
- **Provenance in every cell:** every row you plot must keep its `paper` (sha256),
  `parser`, and `page` columns so the human can trace any point back to the PDF.
  A chart without provenance is not acceptable.
- Charts use `plotly.graph_objects` (NOT `plotly.express`, which needs pandas).
  Feed it plain Python lists built from the SPARQL rows — no dataframe library.
- Do not fabricate or fuse: an RDE η@10 and a PEMWE cell voltage are different
  quantities; never plot them on one axis. See the domain skill's "common traps".

## Suggested cells
1. Imports + store path + the SPARQL SELECT (value, unit, paper, parser, page).
2. Overpotential histogram (`go.Histogram`).
3. Tafel-vs-overpotential scatter (`go.Scatter`, mode="markers").
4. A provenance table (`go.Table`) listing paper/parser/page per point.
```

`skills/general/notebook-analysis/references/notebook_template.py`:

```python
"""marimo notebook skeleton — analysis of the palimpsest RDF graph.

Adapt: change STORE_PATH and the SPARQL query. Spawn via open_notebook; never
run headless. Charts use plotly.graph_objects (no pandas).
"""

import marimo

app = marimo.App()


@app.cell
def _():
    import plotly.graph_objects as go

    from palimpsest.store import RDFStore

    STORE_PATH = "store"
    QUERY = """
    PREFIX pmp: <https://palimpsest.local/schema/>
    SELECT ?value ?unit ?paper ?parser ?page WHERE {
      ?m a pmp:Overpotential ;
         pmp:value ?value ; pmp:unit_label ?unit ;
         pmp:evidence ?e .
      ?e pmp:paper ?paper ; pmp:parser_name ?parser ; pmp:page ?page .
    }
    """
    rows = list(RDFStore(STORE_PATH).sparql(QUERY))
    return go, rows


@app.cell
def _(go, rows):
    values = [float(r["value"]) for r in rows]
    fig = go.Figure(data=[go.Histogram(x=values)])
    fig.update_layout(title="Overpotential distribution", xaxis_title="value")
    fig
    return


if __name__ == "__main__":
    app.run()
```

(The SPARQL prefix/predicate IRIs and the `RDFStore.sparql` row shape are
illustrative — the agent adapts them to the live schema when generating a real
notebook. The test only `ast.parse`s this file.)

- [ ] **Step 4: Create the report-writing skill**

`skills/general/report-writing/SKILL.md`:

```markdown
---
name: report-writing
description: Generate a self-contained HTML report from the extracted RDF graph — SPARQL-backed figures (plotly), a provenance table, and the domain caveats — for sharing or the thesis. Use when the researcher wants a shareable summary rather than an interactive notebook.
when_to_use: user asks for a report, summary, or shareable export of the extracted graph
version: 1.0.0
kind: task
reads:
  - Overpotential
  - TafelSlope
  - MassActivity
  - Stability
  - Evidence
  - Paper
uses:
  - sparql_query
  - write_file
---

# Report-writing playbook

Produce a **self-contained HTML** report into `workspace/reports/`. Write it with
`write_file`; do not spawn anything.

## Discipline
- Start from `references/report_template.py`; change only the SPARQL queries and
  the prose. Each figure is `plotly.graph_objects` embedded via `fig.to_html(
  full_html=False, include_plotlyjs="cdn")` — no kaleido, no static images.
- **Every figure carries a provenance table** (paper sha256, parser, page) for
  the points it shows. A number without provenance does not go in the report.
- Pull the caveats from the domain skill's "common traps": never fuse RDE and
  PEMWE stability; always state iR-correction status and electrolyte.
- Do not fabricate. If the graph lacks a metric, say so — do not invent it.
```

`skills/general/report-writing/references/report_template.py`:

```python
"""HTML report skeleton over the palimpsest RDF graph.

Adapt: change STORE_PATH, the SPARQL queries, and the prose. Emits a single
self-contained HTML file. plotly.graph_objects only (no pandas, no kaleido).
"""

import plotly.graph_objects as go

from palimpsest.store import RDFStore

STORE_PATH = "store"
OUT = "workspace/reports/report.html"

QUERY = """
PREFIX pmp: <https://palimpsest.local/schema/>
SELECT ?value ?paper ?parser ?page WHERE {
  ?m a pmp:Overpotential ; pmp:value ?value ; pmp:evidence ?e .
  ?e pmp:paper ?paper ; pmp:parser_name ?parser ; pmp:page ?page .
}
"""


def build() -> str:
    rows = list(RDFStore(STORE_PATH).sparql(QUERY))
    values = [float(r["value"]) for r in rows]
    fig = go.Figure(data=[go.Histogram(x=values)])
    table = go.Figure(
        data=[go.Table(
            header=dict(values=["paper", "parser", "page"]),
            cells=dict(values=[
                [r["paper"] for r in rows],
                [r["parser"] for r in rows],
                [r["page"] for r in rows],
            ]),
        )]
    )
    parts = [
        "<h1>OER extraction report</h1>",
        fig.to_html(full_html=False, include_plotlyjs="cdn"),
        "<h2>Provenance</h2>",
        table.to_html(full_html=False, include_plotlyjs=False),
    ]
    return "<html><body>" + "\n".join(parts) + "</body></html>"


if __name__ == "__main__":
    from pathlib import Path

    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    Path(OUT).write_text(build(), encoding="utf-8")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pixi run pytest tests/test_general_skills.py tests/test_skills.py -q`
Expected: PASS — both skills register, `check_skill` PASSes for each (every `reads:` class and `uses:` tool is real), and both skeletons `ast.parse`.

- [ ] **Step 6: Full regression + commit**

Run: `pixi run pytest tests/ -q -m "not slow"`
Expected: PASS.

```bash
git add skills/general tests/test_general_skills.py
git commit -m "feat(skills): add notebook-analysis + report-writing general task skills"
```

---

## Self-Review (completed by plan author)

- **Spec coverage:** §4.0 decouple → Task 1. §4.1 `kind:` → Tasks 2/4. §4.2 layout/glob → Tasks 1 (glob) + 6 (move). §4.3 reads/uses gate (hard reads, lazy uses, check_skill reporting) → Tasks 2/3/4. §4.4 two task skills + skeletons → Task 7. §4.5 grouped manifest → Task 5. §5 invariants → Global Constraints (no new tool; read-only). §7 verification items → Tasks 1 (relocation), 3 (bad-uses via load/names), 2 (Evidence reads), 4 (check_skill PASS), 7 (ast.parse). All covered.
- **Placeholder scan:** none — every code step carries full code; commands carry expected output.
- **Type consistency:** `skill_dir`/`all_classes`/`check_reads`/`_ensure_finalized`/`ToolCheck`/`SkillReport.tool_checks`/`SkillReport.kind` are defined where first used and referenced consistently downstream. `_skills[name]["kind"]` set in Task 2, consumed in Tasks 3/5.
- **Dependency check:** skeletons use only `marimo` + `plotly.graph_objects` (in `pixi.toml`); no pandas/polars/matplotlib/kaleido.
