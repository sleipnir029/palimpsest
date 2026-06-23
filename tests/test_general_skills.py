"""The two general/ task skills load, pass the gate, and ship parseable skeletons."""

from __future__ import annotations

import ast
from pathlib import Path

from palimpsest.skill_check import render_report, validate_skill
from palimpsest.skills import SkillLoader


def test_general_skills_registered_not_quarantined():
    loader = SkillLoader()
    names = loader.names()
    for n in ("notebook-analysis", "report-writing"):
        assert n in names, f"{n} should be registered"
        assert n not in loader.invalid


def test_general_skills_check_skill_passes():
    loader = SkillLoader()
    for n in ("notebook-analysis", "report-writing"):
        report = validate_skill(n, loader, resolve_iris=False)
        assert report.kind == "task"
        assert report.ok, render_report(report)


def test_reference_skeletons_parse():
    for p in (
        "skills/general/notebook-analysis/references/notebook_template.py",
        "skills/general/report-writing/references/report_template.py",
    ):
        ast.parse(Path(p).read_text(encoding="utf-8"))
