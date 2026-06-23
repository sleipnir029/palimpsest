"""T69 — skill ↔ schema ↔ ontology consistency gate.

The gate is the *deterministic detector*: a skill declares `targets:` (schema
Measurement classes it extracts); the gate confirms each exists in the schema
(offline, hard) and that its EMMO/H2KG IRIs resolve (network, advisory).

Fail mode (agreed 2026-06-19): a skill targeting a non-existent class is
*quarantined* (not registered, loudly warned) — the agent stays up so a future
corrector layer can self-heal it. Unresolved IRIs only warn, via `check_skill`.
"""

from __future__ import annotations

import pytest
import yaml

from palimpsest.skill_check import (
    check_targets,
    measurement_classes,
    render_report,
    validate_skill,
)
from palimpsest.skills import SkillLoader
from palimpsest.tools.check_skill import check_skill

# The 8 schema Measurement classes the OER skill body teaches (SKILL.md:23-30).
OER_TARGETS = [
    "Overpotential",
    "TafelSlope",
    "MassActivity",
    "TurnoverFrequency",
    "ECSA",
    "ExchangeCurrentDensity",
    "SpecificActivity",
    "Stability",
]

# T71 — the PEMWE-anode overlay reuses the 8 OER classes and adds the two
# full-cell classes its body teaches (SKILL.md targets:).
PEMWE_TARGETS = OER_TARGETS + ["PEMWECellVoltage", "DegradationRate"]


def _write_skill(root, name, *, targets=None):
    """Materialize a minimal `<root>/<name>/SKILL.md` for loader tests."""
    d = root / name
    d.mkdir(parents=True)
    fm = {
        "name": name,
        "description": "test skill",
        "when_to_use": "test",
        "version": "1.0.0",
    }
    if targets is not None:
        fm["targets"] = targets
    body = "# body\n\n" + ("filler line for the >1000 char body. " * 60)
    (d / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + body,
        encoding="utf-8",
    )
    return d


# ---- offline: schema membership -------------------------------------------

def test_measurement_classes_are_the_schema_subclasses():
    mc = measurement_classes()
    for name in OER_TARGETS + ["ChargeTransferCoefficient"]:
        assert name in mc, f"{name} should be a Measurement subclass"
    # the abstract base and non-Measurement classes are excluded
    for name in ["Measurement", "Paper", "Condition", "Evidence", "Electrolyte"]:
        assert name not in mc


def test_oer_skill_declares_expected_targets():
    from pathlib import Path

    from palimpsest.skills import _split

    meta, _ = _split(
        Path("skills/oer-extraction/SKILL.md").read_text(encoding="utf-8")
    )
    assert set(meta.get("targets") or []) == set(OER_TARGETS)


def test_check_targets_all_present_returns_empty():
    assert check_targets("oer-extraction", OER_TARGETS) == []


def test_check_targets_names_the_missing_class():
    missing = check_targets("x", ["Overpotential", "NoSuchClass"])
    assert missing == ["NoSuchClass"]


def test_real_oer_skill_membership_passes():
    report = validate_skill("oer-extraction", SkillLoader(), resolve_iris=False)
    assert report.missing_classes == []
    assert report.ok


def test_pemwe_skill_declares_expected_targets():
    from pathlib import Path

    from palimpsest.skills import _split

    meta, _ = _split(
        Path("skills/pemwe-anode/SKILL.md").read_text(encoding="utf-8")
    )
    assert set(meta.get("targets") or []) == set(PEMWE_TARGETS)


def test_pemwe_targets_are_real_measurement_classes():
    # the T71 additions resolve as Measurement subclasses (gate's offline half)
    mc = measurement_classes()
    for name in ["PEMWECellVoltage", "DegradationRate"]:
        assert name in mc, f"{name} should be a Measurement subclass"
    assert check_targets("pemwe-anode", PEMWE_TARGETS) == []


def test_real_pemwe_skill_membership_passes_and_not_quarantined():
    loader = SkillLoader()
    assert "pemwe-anode" in loader.names()
    assert "pemwe-anode" not in loader.invalid
    report = validate_skill("pemwe-anode", loader, resolve_iris=False)
    assert report.missing_classes == []
    assert report.ok


# ---- offline: loader quarantine -------------------------------------------

def test_loader_quarantines_skill_with_bad_target(tmp_path):
    _write_skill(tmp_path, "broken", targets=["Overpotential", "NoSuchClass"])
    with pytest.warns(UserWarning, match="NoSuchClass"):
        loader = SkillLoader(root=tmp_path)
    assert "broken" not in loader.names()
    assert "broken" in loader.invalid
    assert "NoSuchClass" in loader.invalid["broken"]


def test_loader_keeps_skill_with_valid_targets(tmp_path):
    _write_skill(tmp_path, "good", targets=["Overpotential", "Stability"])
    loader = SkillLoader(root=tmp_path)
    assert "good" in loader.names()
    assert loader.invalid == {}


def test_loader_skill_without_targets_is_unaffected(tmp_path):
    _write_skill(tmp_path, "legacy", targets=None)
    loader = SkillLoader(root=tmp_path)
    assert "legacy" in loader.names()
    assert loader.invalid == {}


def test_validate_skill_reports_quarantined_skill_not_keyerror(tmp_path):
    """The corrector-survives-quarantine contract the deviation rests on:
    a quarantined skill is still introspectable (in _meta), so validate_skill
    returns a FAIL report naming the bad class rather than raising KeyError."""
    _write_skill(tmp_path, "broken", targets=["Overpotential", "NoSuchClass"])
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        loader = SkillLoader(root=tmp_path)
    report = validate_skill("broken", loader, resolve_iris=False)
    assert report.missing_classes == ["NoSuchClass"]
    assert not report.ok


def test_unresolved_external_iri_warns_offline(monkeypatch):
    """Advisory IRI path (€0, no network): if a real target's external IRI
    fails to resolve, it lands in unresolved_iris and the report is not ok."""
    from palimpsest import ontology

    monkeypatch.setattr(ontology, "echo_iri_exists", lambda iri: False)
    monkeypatch.setattr(ontology, "h2kg_iri", lambda frag: None)
    report = validate_skill("oer-extraction", SkillLoader(), resolve_iris=True)
    assert report.missing_classes == []  # all targets still in schema
    assert report.unresolved_iris  # but their emmo:/h2kg: IRIs "don't resolve"
    assert not report.ok


# ---- the check_skill tool --------------------------------------------------

def test_check_skill_unknown_name_is_friendly():
    out = check_skill("does-not-exist")
    assert "unknown skill" in out.lower()


def test_render_report_marks_a_clean_skill_pass():
    report = validate_skill("oer-extraction", SkillLoader(), resolve_iris=False)
    assert "PASS" in render_report(report)


# ---- network (slow): IRI resolution via ontology.py ------------------------

@pytest.mark.slow
def test_real_oer_skill_iris_resolve():
    report = validate_skill("oer-extraction", SkillLoader(), resolve_iris=True)
    assert report.unresolved_iris == [], report.unresolved_iris
    assert report.ok


@pytest.mark.slow
def test_check_skill_tool_renders_pass_for_real_skill():
    out = check_skill("oer-extraction")
    assert "oer-extraction" in out
    assert "PASS" in out


@pytest.mark.slow
def test_real_pemwe_skill_iris_resolve():
    # T71: the two new classes' h2kg close_mappings (CellVoltage,
    # CellVoltageIncreaseRate) resolve, as do the reused classes' IRIs.
    report = validate_skill("pemwe-anode", SkillLoader(), resolve_iris=True)
    assert report.unresolved_iris == [], report.unresolved_iris
    assert report.ok


# ---- task-skill: kind/reads load-gate (Task 2) ----------------------------

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
    assert loader._skills["good-task"]["kind"] == "task"


def test_legacy_skill_defaults_to_extraction_kind(tmp_path):
    _write_skill(tmp_path / "domain", "legacy", targets=["Overpotential"])
    loader = SkillLoader(root=tmp_path)
    assert loader._skills["legacy"]["kind"] == "extraction"


def test_task_skill_with_bad_reads_is_quarantined(tmp_path):
    _write_task_skill(tmp_path / "general", "bad-reads",
                      reads=["Overpotential", "NoSuchClass"], uses=["sparql_query"])
    with pytest.warns(UserWarning, match="NoSuchClass"):
        loader = SkillLoader(root=tmp_path)
    assert "bad-reads" not in loader.names()
    assert "bad-reads" in loader.invalid


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


# ---- task-skill: validate_skill + render_report (Task 4) -------------------

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
