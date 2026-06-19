"""T69 — skill ↔ schema ↔ ontology consistency gate (deterministic detector).

A skill declares `targets:` (the schema Measurement classes it extracts). This
module verifies that declaration, in code, at skill-load time:

  (a) membership — each target is a real Measurement subclass in
      `schema/palimpsest.yaml` (offline, hard: a miss means extraction can't
      work, so `SkillLoader` quarantines the skill);
  (b) IRI resolution — each target's `emmo:`/`h2kg:` IRIs (class_uri +
      close_mappings) resolve in the live ontologies via `ontology.py`
      (network, advisory: surfaced on demand by the `check_skill` tool).

The match is EXACT on purpose. Both sides — the skill's declaration and the
schema — are our own controlled vocabulary, so a fuzzy match would hide drift
and defeat the gate (cf. the F2 incident). Synonym/unit handling against messy
paper text is a separate, LLM-driven concern that lives in extract.py +
normalize.py, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import yaml

from . import ontology

_SCHEMA = Path("schema/palimpsest.yaml")


@cache
def _schema_doc() -> dict:
    return yaml.safe_load(_SCHEMA.read_text(encoding="utf-8"))


@cache
def measurement_classes() -> dict[str, dict]:
    """`{class_name: {class_uri, close_mappings}}` for every `is_a: Measurement`.

    The abstract `Measurement` base (no `is_a`) and non-measurement classes
    (Paper, Condition, Evidence, …) are excluded — `targets:` are the concrete
    measurement subclasses an extraction emits.
    """
    out: dict[str, dict] = {}
    for name, body in (_schema_doc().get("classes") or {}).items():
        if body and body.get("is_a") == "Measurement":
            out[name] = {
                "class_uri": body.get("class_uri"),
                "close_mappings": list(body.get("close_mappings") or []),
            }
    return out


def schema_prefixes() -> dict[str, str]:
    return dict(_schema_doc().get("prefixes") or {})


def check_targets(skill_name: str, targets: list[str]) -> list[str]:
    """Offline membership check: targets that are not Measurement classes.

    Takes `targets` as an argument (not a SkillLoader) so `SkillLoader` can call
    it during its own construction without reconstructing a loader.
    """
    mc = measurement_classes()
    return [t for t in targets if t not in mc]


@dataclass
class ClassCheck:
    name: str
    in_schema: bool
    external_iris: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


@dataclass
class SkillReport:
    skill: str
    checks: list[ClassCheck]
    iris_resolved: bool

    @property
    def missing_classes(self) -> list[str]:
        return [c.name for c in self.checks if not c.in_schema]

    @property
    def unresolved_iris(self) -> list[tuple[str, str]]:
        return [(c.name, iri) for c in self.checks for iri in c.unresolved]

    @property
    def ok(self) -> bool:
        return not self.missing_classes and not self.unresolved_iris


def _prefix_local(curie: str) -> tuple[str, str]:
    if ":" not in curie:
        return "", curie
    prefix, local = curie.split(":", 1)
    return prefix, local


def _resolves(prefix: str, local: str) -> bool:
    """Resolve one external CURIE via ontology.py. Only emmo:/h2kg: are external."""
    if prefix == "emmo":
        base = schema_prefixes().get("emmo", "")
        return ontology.echo_iri_exists(base + local)
    if prefix == "h2kg":
        return ontology.h2kg_iri(local) is not None
    return True  # palimpsest-local or non-external — nothing to resolve


def validate_skill(name: str, loader, *, resolve_iris: bool = True) -> SkillReport:
    """Full report for one skill's `targets:`. Raises KeyError if unknown.

    `resolve_iris=False` keeps it offline (membership only) — what `SkillLoader`
    needs at load. `resolve_iris=True` also resolves EMMO/H2KG IRIs (network) —
    what the on-demand `check_skill` tool uses; an unresolved IRI is advisory
    (warn), a missing class is hard.
    """
    meta = loader._meta.get(name)
    if meta is None:
        raise KeyError(name)
    targets = list(meta.get("targets") or [])
    mc = measurement_classes()

    checks: list[ClassCheck] = []
    for t in targets:
        if t not in mc:
            checks.append(ClassCheck(name=t, in_schema=False))
            continue
        external: list[str] = []
        unresolved: list[str] = []
        if resolve_iris:
            candidates = []
            if mc[t]["class_uri"]:
                candidates.append(mc[t]["class_uri"])
            candidates.extend(mc[t]["close_mappings"])
            for curie in candidates:
                prefix, local = _prefix_local(curie)
                if prefix not in ("emmo", "h2kg"):
                    continue
                external.append(curie)
                if not _resolves(prefix, local):
                    unresolved.append(curie)
        checks.append(
            ClassCheck(
                name=t, in_schema=True, external_iris=external, unresolved=unresolved
            )
        )
    return SkillReport(skill=name, checks=checks, iris_resolved=resolve_iris)


def render_report(report: SkillReport) -> str:
    """Human/agent-readable PASS/FAIL with a per-class line."""
    status = "PASS" if report.ok else "FAIL"
    lines = [f"check_skill {report.skill!r}: {status}"]
    for c in report.checks:
        if not c.in_schema:
            lines.append(f"  ✗ {c.name}: NOT in schema (no such Measurement class)")
        elif c.unresolved:
            lines.append(
                f"  ⚠ {c.name}: in schema; unresolved IRIs: {', '.join(c.unresolved)}"
            )
        elif c.external_iris:
            lines.append(f"  ✓ {c.name}: in schema ({len(c.external_iris)} IRI ok)")
        else:
            lines.append(f"  ✓ {c.name}: in schema (palimpsest-local, no external IRI)")
    if not report.checks:
        lines.append("  (skill declares no targets:)")
    if not report.iris_resolved:
        lines.append("  (offline: IRIs not checked)")
    return "\n".join(lines)
