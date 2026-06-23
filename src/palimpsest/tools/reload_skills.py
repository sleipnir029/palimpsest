"""`reload_skills` tool — rescan skills/ so an agent-authored skill becomes visible."""
from __future__ import annotations

from . import register
from .read_skill import _LOADER  # the one process-wide SkillLoader


@register("reload_skills", {
    "description": (
        "Rescan the skills/ directory so a skill you just authored (wrote a new "
        "SKILL.md) becomes visible to read_skill/check_skill. Returns the refreshed "
        "skill manifest. Read-only, €0."
    ),
    "input_schema": {"type": "object", "properties": {}},
})
def reload_skills() -> str:
    _LOADER.reload()
    return _LOADER.manifest() or "(no skills)"
