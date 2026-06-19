# T69 — Skill ↔ schema ↔ ontology consistency gate

**Status:** planned · **Group:** constrained-autonomy (thesis core) · **Priority:** high

## Bigger picture (read first)
The thesis contribution is the **constrained-autonomy agent**: competence enforced in
code, not borrowed from the human + Claude Code who built it. Today a skill's mapping
from domain concept → schema class is **hand-typed prose in `SKILL.md`** and drifts
silently — it already broke once (F2: the OER skill table pointed at deleted schema
slots; caught by a human reviewer, not the agent). When palimpsest runs on a new
domain *without Claude Code present*, that human safety net is gone. This card makes
the skill↔schema↔ontology link **checkable in code at load time**, so authoring a new
domain skill (T71) becomes verifiable rather than hopeful. Pairs with T62
(`describe_schema`, the read side) and is the precondition the meeting asked for:
*"how are skills created for a domain and how do we know they're correct?"*
See `report/supervisor-answers-2026-06-19.md` §2 (mechanism #1 and #3) and the plan
`~/.claude/plans/so-i-had-a-snappy-lark.md`.

## Why
A malformed skill (names a class/slot/IRI that doesn't exist in the schema or doesn't
resolve in EMMO/H2KG) currently fails *silently* — extractions just come back wrong or
empty, with no signal that the skill itself is inconsistent. Make it fail **loud at
skill-load**, not at extraction time.

## Current situation
- `src/palimpsest/skills.py` `SkillLoader`: parses `SKILL.md` YAML frontmatter
  (`name`, `description`, `when_to_use`, `version`) and loads the prose body on
  `read_skill`. **No structural declaration** of which measurement classes the skill
  targets, and **no check** against the schema.
- `schema/palimpsest.yaml` holds the measurement classes with `class_uri` +
  `close_mappings` (EMMO/H2KG). `schema/generated/` has the resolved structure
  (`_CLASS_MAP` / pydantic).
- `src/palimpsest/ontology.py` (`emmo_iri()`, `KNOWN_IRIS`, ECHO fetch) can resolve
  IRIs but is **only invoked at schema-generation time** (T18/T19), never at runtime.
- H2KG alignment exists in the schema (T47, done) but `ontology.py` has no H2KG
  resolver yet (its T47 live test fetches the H2KG TTL — reuse that path).

## What to build
1. **Declared alignment in the skill.** Add a machine-readable block to `SKILL.md`
   frontmatter (or a sibling `alignment.yaml`): the list of schema measurement classes
   the skill targets, e.g. `targets: [Overpotential, TafelSlope, ECSA, ...]`, and
   optionally the claimed target ontology (`ontology: h2kg`). Backfill it for
   `skills/oer-extraction/`.
2. **A gate function** `validate_skill(name) -> Report` (in `skills.py` or a new
   `skill_check.py`) that, for each declared class: (a) confirms it exists in
   `schema/palimpsest.yaml` / the generated class map; (b) confirms its `class_uri`
   or `close_mapping` resolves via `ontology.py` (extend with an H2KG resolver reusing
   T47's TTL fetch+cache). Returns a structured pass/fail with per-class reasons.
3. **Wire it** so `SkillLoader` runs the gate at load (raise/warn loud on failure) and
   expose a `check_skill(name)` read-only `@register` tool so the agent can run it on
   demand. Fail mode is the design decision — recommend: raise on a missing class
   (hard inconsistency), warn on an unresolved IRI (network/ontology drift).

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_skill_check.py -q
# fixture skill declaring a non-existent class → gate FAILS with that class named;
# real skills/oer-extraction/ → gate PASSES (all declared classes in schema).
```

## Will touch
- `src/palimpsest/skills.py` (gate at load) and/or `src/palimpsest/skill_check.py` (new)
- `src/palimpsest/ontology.py` (add H2KG resolver; reuse T47 TTL fetch/cache)
- `skills/oer-extraction/SKILL.md` (add `targets:` alignment block)
- `src/palimpsest/tools/` + `tools/__init__.py` (new `check_skill` tool)
- `tests/test_skill_check.py` (new) — broken-skill fixture + real-skill pass

## Out of scope
- Auto-generating the alignment block from prose → that's authoring, stays
  human+LLM (T71).
- Auto-fixing a failing skill → the agent/human re-authors; the gate only detects.
- Driving extraction off the declared targets (it stays advisory metadata for now).
