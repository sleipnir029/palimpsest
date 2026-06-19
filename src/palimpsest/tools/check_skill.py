"""`check_skill` tool — verify a skill's `targets:` against schema + ontologies.

The read side of T69's constrained-autonomy spine: the agent can ask, at run
time, whether a skill is consistent with the schema (each declared target is a
real Measurement class) and whether its EMMO/H2KG IRIs still resolve. Read-only,
€0 (no LLM call); the IRI resolution is the network path (advisory warnings),
membership is offline+hard (already enforced at load by SkillLoader quarantine).
"""

from __future__ import annotations

from palimpsest.skill_check import render_report, validate_skill

from . import register
from .read_skill import _LOADER  # one process-wide SkillLoader; do not make another


@register("check_skill", {
    "description": (
        "Check a skill's declared `targets:` against the schema and ontologies "
        "(read-only). Reports, per target class, whether it exists in the schema "
        "and whether its EMMO/H2KG IRIs resolve."
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
