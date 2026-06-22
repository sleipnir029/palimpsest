# T83 — Domain skill expansion: enrich OER + add a second domain

## Why
Skill-extensibility is palimpsest's intended growth path and a **thesis contribution**
(CLAUDE.md: "new extraction domains ship as new SKILL.md folders"; T71 counted the
"live skill-creation-method proof"). More domain coverage is demoable autonomy — and
the strongest version has the **constrained-autonomy agent author the skill itself**,
which IS the thesis core (self-extension within enforced bounds).

## Input state
- `skills/oer-extraction/SKILL.md`, `skills/pemwe-anode/SKILL.md`.
- `check_skill` gate (T69) validates `targets:` against `schema/palimpsest.yaml`;
  IRIs must resolve. Central+overlay pattern for shared vs per-domain content (memory).
- `schema/palimpsest.yaml` (main) + `schema/exploratory.yaml` (proposed slots).

## Output state (target) — do in this order
- **(a) Enrich the existing OER skill** — lowest friction, no schema change: tighten the
  playbook, add under-covered slots/conditions that already exist as schema classes,
  re-verify with `check_skill`. Immediate value.
- **(b) Add ONE new domain** (HER *or* CO2RR) as `skills/<domain>/SKILL.md`. If its
  measurement classes are NOT in `schema/palimpsest.yaml`, propose them in
  `schema/exploratory.yaml` FIRST (never silently edit the main schema), then have the
  skill `target:` them. Use the central+overlay merge, not duplication.
- **(c) Thesis demo (optional):** have the AGENT author/enrich the skill via
  `write_file` (workspace-confined) + `check_skill` — capture the workspace fence + gate
  pass as evidence of constrained self-extension.

## Verification
- `check_skill('<domain>-extraction')` passes (targets resolve to schema classes; IRIs
  resolve) for each new/edited skill.
- `extract_paper` on a paper in the new domain inserts measurements WITH provenance
  (paper_hash, parser, page, bbox, run_id); `graph_summary` shows the new classes.
- (c): the agent-authored run shows the write confined to the workspace and the gate
  catching any mis-targeted slot.

## Will touch
- `skills/<domain>/SKILL.md` (new), `skills/oer-extraction/SKILL.md` (enrich),
  `schema/exploratory.yaml` (proposed new slots, if the domain needs them).

## Will NOT touch
- `schema/palimpsest.yaml` for un-vetted slots — proposals go through
  `schema/exploratory.yaml` first (the T69 gate + CLAUDE.md enforce this).
- The pipeline / provenance machinery (a new domain rides the existing path).
