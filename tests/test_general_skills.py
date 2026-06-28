"""The two general/ task skills load, pass the gate, and ship parseable skeletons."""

from __future__ import annotations

import ast
from pathlib import Path

from palimpsest.skill_check import render_report, validate_skill
from palimpsest.skills import SkillLoader
from schema.generated.pydantic import Condition, Evidence, Overpotential, Paper
from palimpsest.store import RDFStore


def test_general_skills_registered_not_quarantined():
    loader = SkillLoader()
    names = loader.names()
    for n in ("notebook-analysis", "report-writing", "marimo-pairing"):
        assert n in names, f"{n} should be registered"
        assert n not in loader.invalid


def test_general_skills_check_skill_passes():
    loader = SkillLoader()
    for n in ("notebook-analysis", "report-writing", "marimo-pairing"):
        report = validate_skill(n, loader, resolve_iris=False)
        assert report.kind == "task"
        assert report.ok, render_report(report)


def test_reference_skeletons_parse():
    for p in (
        "skills/general/notebook-analysis/references/notebook_template.py",
        "skills/general/report-writing/references/report_template.py",
    ):
        ast.parse(Path(p).read_text(encoding="utf-8"))


def _make_overpotential() -> Overpotential:
    evidence = Evidence(
        paper=Paper(sha256="abc123", doi="10.1000/xyz", title="A paper"),
        page=3,
        bbox_x0=0.1, bbox_y0=0.2, bbox_x1=0.3, bbox_y1=0.4,
        parser_name="mineru",
        source_text="η = 236 mV at 10 mA/cm²",
    )
    return Overpotential(
        value=236.0,
        unit_label="mV",
        condition=Condition(current_density=10.0, temperature_C=25.0),
        evidence=evidence,
    )


def _extract_sparql(path: str) -> str:
    """Extract the single SPARQL query literal from a skeleton file via AST."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    queries = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "SELECT" in node.value
        and "WHERE" in node.value
    ]
    assert len(queries) == 1, (
        f"Expected exactly 1 SPARQL literal in {path}, got {len(queries)}"
    )
    return queries[0]


def test_notebook_skeleton_query_returns_real_rows():
    store = RDFStore()
    store.insert_extraction(_make_overpotential(), run_id="r1")

    q = _extract_sparql(
        "skills/general/notebook-analysis/references/notebook_template.py"
    )
    rows = store.sparql(q)
    assert len(rows) >= 1
    assert float(rows[0]["value"]) == 236.0


def test_report_skeleton_query_returns_real_rows():
    store = RDFStore()
    store.insert_extraction(_make_overpotential(), run_id="r1")

    q = _extract_sparql(
        "skills/general/report-writing/references/report_template.py"
    )
    rows = store.sparql(q)
    assert len(rows) >= 1
    assert float(rows[0]["value"]) == 236.0
    assert rows[0]["paper"] is not None
    assert rows[0]["parser"] is not None
    assert rows[0]["page"] is not None
