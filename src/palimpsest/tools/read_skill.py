"""`read_skill` tool — loads a skill's body on demand.

The system prompt advertises available skills via `SkillLoader.manifest()`;
this tool lets the agent pull the full body in for the relevant skill only,
keeping the cached prompt small.
"""

from __future__ import annotations

from palimpsest.skills import SkillLoader

from . import register

# One loader per process — `Path("skills")` is relative to CWD (repo root,
# the project convention for pytest / `pixi run` / `python -m palimpsest`).
_LOADER = SkillLoader()


@register("read_skill", {
    "description": "Load the full body of a skill by name. Available skills are listed in the system prompt.",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
})
def read_skill(name: str) -> str:
    try:
        return _LOADER.load(name)
    except KeyError:
        avail = ", ".join(sorted(_LOADER._skills)) or "(none)"
        return f"unknown skill: {name!r}. Available: {avail}"
