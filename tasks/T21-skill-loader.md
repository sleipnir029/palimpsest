# T21 — Skill loader (read_skill tool)

## Why
Progressive disclosure — only skill frontmatter is in the system prompt, body loaded by agent when needed.

## Input state
- T20 merged. SKILL.md exists with valid frontmatter.
- T06 (TOOLS registry) merged.

## Output state
- File `src/palimpsest/skills.py` exports:
  - Class `SkillLoader`:
    - `__init__(self, root: Path = Path("skills"))` — scans `*/SKILL.md`, parses frontmatter only.
    - `def manifest(self) -> str` — returns a string listing all skills as `- {name}: {description}` for injection into system prompt.
    - `def load(self, name: str) -> str` — returns the body of the named SKILL.md (without frontmatter).
- File `src/palimpsest/tools/read_skill.py`:
  - `def read_skill(name: str) -> str` — calls SkillLoader.load.
  - Registered in TOOLS with schema `{"name": "read_skill", "description": "Load the full body of a skill by name. Available skills are listed in the system prompt.", "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}`.
- File `tests/test_skills.py` covers: manifest returns string with oer-extraction listed, load returns body > 1000 chars.

## Verification
```bash
pixi run pytest tests/test_skills.py -v
```

## Will touch
- `src/palimpsest/skills.py` (full)
- `src/palimpsest/tools/read_skill.py` (new)
- `src/palimpsest/tools/__init__.py` (edit: import read_skill)
- `tests/test_skills.py` (new)

## Will NOT touch
- skills/oer-extraction/SKILL.md (T20 stable).
- agent.py (system_prompt is set by __main__, not by agent.py).

## Out of scope
- Loading skills into __main__ system prompt → T22 will wire this.
- Multi-skill blending → future.

## Notes / references
- Use `yaml.safe_load` on the frontmatter between `---` markers.
- The `manifest()` output should be ~50–100 tokens per skill. Don't include the body.
