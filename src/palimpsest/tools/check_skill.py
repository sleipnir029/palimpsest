"""`check_skill` tool — verify a skill against schema + ontologies.

For extraction skills: checks each `targets:` class against the schema and
whether its EMMO/H2KG IRIs resolve. For task skills: reports validity of
`reads:` (schema classes) and `uses:` (registered tools). Read-only, €0.
"""

from __future__ import annotations

from palimpsest.skill_check import render_report, validate_skill

from . import register
from .read_skill import _LOADER  # one process-wide SkillLoader; do not make another


@register("check_skill", {
    "description": (
        "Check a skill's validity (read-only, €0). For extraction skills, reports "
        "each `targets:` class against the schema and EMMO/H2KG IRI resolution. "
        "For task skills (`kind: task`), reports whether `reads:` schema classes "
        "and `uses:` registered tools are valid."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
})
def check_skill(name: str) -> str:
    try:
        report = validate_skill(name, _LOADER, resolve_iris=True)
    except KeyError:
        avail = ", ".join(_LOADER.names()) or "(none)"
        return f"unknown skill: {name!r}. Available: {avail}"
    return render_report(report)
