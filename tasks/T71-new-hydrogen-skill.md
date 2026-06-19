# T71 — New hydrogen domain skill (HER or PEMWE) + ontology alignment

**Status:** planned · **Group:** skill extensibility (thesis contribution #4) · **Priority:** high

## Bigger picture (read first)
The supervisor wants the use-case demo on **broader hydrogen technology**, not just OER
(`meetings/19-06-2026.md`). That decision (confirmed with the user) means we must
actually author a *second* domain skill — which is precisely the proof of contribution
#4 ("a schema strategy that doubles as a skill-creation method") and the live test of
the run-time-autonomy machinery (T62 `describe_schema` + T69 consistency gate). **Honest
framing:** authoring a skill is a human-supervised, LLM-assisted *build-time* method
(Claude or ChatGPT is fine); the autonomy claim is about *running* it, not authoring it.
Do NOT relabel the system "domain-agnostic" — see `report/supervisor-answers-2026-06-19.md`
§0/§2. Ontology is **H2KG** (PEMWE profile), supervisor-mandated; H2KG reuses EMMO ECHO,
so aligning to H2KG also aligns to EMMO.

## Why
One new skill demonstrates domain onboarding end-to-end and supplies the corpus domain
for the scaled demo (T73). It also stress-tests whether "drop in a skill" is really
enough, or whether new measurement classes + alignment are required (expected: some are).

## Corpus reality (read `papers/paper list/*.csv`, 2026-06-19) — decides the sub-domain
The actual working corpus is **overwhelmingly IrO₂/TiO₂ (and Ir-based) anode catalysts
for OER in acidic media / PEM water electrolysis** — nearly every paper across the
student lists is a TiO₂-supported iridium-oxide OER/PEMWE-anode study. So this is **not
HER and not a brand-new domain**: it's a **PEMWE-anode extension of the existing
`oer-extraction` skill**, adding full-cell/durability quantities the single-electrode OER
papers don't carry (cell voltage, catalyst loading mg·cm⁻², degradation rate mV·h⁻¹,
membrane/MEA context). This matches the memory note "central + per-skill overlay, not
duplication" — universals stay central, PEMWE-specific slots go in an overlay.

**Decision (largely resolved by the data):** build a PEMWE-anode skill as an overlay on
OER, not a separate HER skill. Confirm with the user only if they want to broaden beyond
the actual corpus.

## Current situation
- Only `skills/oer-extraction/` exists (`SKILL.md` + `normalization.yaml` +
  `references/`). Loader = `skills.py`; normalization overlay = `normalize.py`.
- Schema (`schema/palimpsest.yaml`) covers OER metrics with EMMO + H2KG mappings
  (T47, done). Central/overlay normalization split exists (universals central,
  per-domain overlay; merger raises on shadowing).
- T62 (`describe_schema`) + T69 (consistency gate) are the tools this skill should be
  authored *against* (author → run gate → fix until green).

## What to build
1. `skills/<domain>/SKILL.md` — frontmatter (`name`, `description`, `when_to_use`,
   `version`) + the `targets:` alignment block (T69) + prose playbook (required slots,
   measurement conditions, conventions, traps), mirroring the OER skill's shape.
2. `skills/<domain>/normalization.yaml` — domain operating points / mechanisms /
   electrolytes / units overlay; must NOT shadow `UNIVERSAL_*` (merger enforces).
3. **Schema additions only if needed:** any genuinely new measurement class →
   add to `schema/palimpsest.yaml` with EMMO `class_uri` + H2KG `close_mapping`
   (follow the T47 pattern; close NOT exact for class↔individual), then
   `pixi run schema` to regenerate `schema/generated/*`. Reuse existing classes where
   the quantity already exists.
4. The new skill must **pass the T69 gate** and smoke-extract on one hydrogen paper.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_skill_check.py -q   # new skill passes the gate
pixi run schema                                                     # exit 0 if schema changed
# (--live) extract one hydrogen paper via the new skill → ≥1 valid measurement, provenance intact
```

## Will touch
- `skills/<domain>/SKILL.md`, `skills/<domain>/normalization.yaml`, `skills/<domain>/references/`
- `schema/palimpsest.yaml` + `schema/generated/*` (only if new classes) — regenerate
- `tests/` (gate test parametrized over the new skill; schema-gen test if schema changed)

## Out of scope
- More than one new domain — exactly one for the thesis demo.
- Claiming general domain-agnosticism — author one, claim nothing about untried fields.
- The corpus run itself → T73.
