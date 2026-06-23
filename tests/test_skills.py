"""T21 — SkillLoader contract tests.

Card asks for two assertions; we add a third for the KeyError contract that
`read_skill`'s tool wrapper depends on.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from palimpsest.normalize import build_normalization_prompt
from palimpsest.skills import SkillLoader


def test_manifest_lists_oer_extraction():
    loader = SkillLoader()
    m = loader.manifest()
    assert isinstance(m, str)
    assert "oer-extraction" in m


def test_load_returns_body_over_1000_chars():
    loader = SkillLoader()
    body = loader.load("oer-extraction")
    assert len(body) > 1000


def test_load_unknown_raises_keyerror():
    loader = SkillLoader()
    with pytest.raises(KeyError):
        loader.load("does-not-exist")


def _write_min_skill(root, name, *, normalization=None):
    """Materialize <root>/<...>/<name>/SKILL.md (+ optional normalization.yaml)."""
    d = root / name
    d.mkdir(parents=True)
    fm = {"name": name, "description": "t", "when_to_use": "t", "version": "1.0.0"}
    body = "# body\n\n" + ("filler. " * 200)
    (d / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + body, encoding="utf-8"
    )
    if normalization is not None:
        (d / "normalization.yaml").write_text(yaml.safe_dump(normalization), encoding="utf-8")
    return d


def test_skill_dir_returns_containing_directory():
    loader = SkillLoader()
    p = loader.skill_dir("oer-extraction")
    assert p.is_dir()
    assert (p / "SKILL.md").exists()


def test_skill_dir_unknown_raises_keyerror():
    loader = SkillLoader()
    with pytest.raises(KeyError):
        loader.skill_dir("does-not-exist")


def test_loader_finds_skills_nested_two_levels(tmp_path):
    """Recursive glob discovers a skill nested under an extra folder (the future
    skills/domain/ and skills/general/ layout)."""
    _write_min_skill(tmp_path / "domain", "nested-skill")
    loader = SkillLoader(root=tmp_path)
    assert "nested-skill" in loader.names()


def test_normalization_overlay_survives_relocation(tmp_path):
    """B1 guard: skill_dir points at the real (possibly relocated) directory, so
    the normalization overlay is found regardless of nesting depth."""
    _write_min_skill(
        tmp_path / "domain", "relocated",
        normalization={"domain": "relocated", "active_metals": ["Ir"]},
    )
    loader = SkillLoader(root=tmp_path)
    block = build_normalization_prompt([loader.skill_dir("relocated")])
    assert "relocated" in block  # overlay was loaded, not silently {}


def _write_task(root, name):
    d = root / name
    d.mkdir(parents=True)
    fm = {"name": name, "description": "task skill", "when_to_use": "t",
          "version": "1.0.0", "kind": "task",
          "reads": ["Overpotential"], "uses": ["sparql_query"]}
    body = "# body\n\n" + ("filler. " * 60)
    (d / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + body, encoding="utf-8"
    )


def test_manifest_groups_domain_and_general(tmp_path):
    _write_min_skill(tmp_path / "domain", "an-extraction")  # kind defaults to extraction
    _write_task(tmp_path / "general", "a-task")
    loader = SkillLoader(root=tmp_path)
    m = loader.manifest()
    assert "**Domain skills**" in m
    assert "**General skills**" in m
    assert "an-extraction" in m and "a-task" in m
    # domain section precedes general section
    assert m.index("**Domain skills**") < m.index("**General skills**")


# --- reload() tests ---------------------------------------------------------

def test_reload_picks_up_new_skill(tmp_path):
    """A skill written after construction becomes visible after reload()."""
    _write_min_skill(tmp_path, "skill-alpha")
    loader = SkillLoader(root=tmp_path)
    assert "skill-beta" not in loader.names()

    _write_min_skill(tmp_path, "skill-beta")
    loader.reload()
    assert "skill-beta" in loader.names()


def test_reload_resets_finalized(tmp_path):
    """reload() resets _finalized so the uses-gate runs again on next access."""
    _write_min_skill(tmp_path, "skill-alpha")
    loader = SkillLoader(root=tmp_path)
    loader.names()  # triggers _ensure_finalized → _finalized = True
    assert loader._finalized is True

    loader.reload()
    assert loader._finalized is False


def test_reload_clears_stale_quarantine(tmp_path):
    """A skill quarantined for bad reads: is accepted after reload() once fixed."""
    d = tmp_path / "bad-task"
    d.mkdir()
    bad_fm = {
        "name": "bad-task",
        "description": "task skill",
        "when_to_use": "t",
        "version": "1.0.0",
        "kind": "task",
        "reads": ["NonExistentClass999"],
        "uses": ["sparql_query"],
    }
    body = "# body\n\n" + ("filler. " * 60)
    skill_file = d / "SKILL.md"
    skill_file.write_text(
        "---\n" + yaml.safe_dump(bad_fm, sort_keys=False) + "---\n\n" + body,
        encoding="utf-8",
    )

    with pytest.warns(UserWarning, match="quarantined"):
        loader = SkillLoader(root=tmp_path)

    assert "bad-task" in loader.invalid
    assert "bad-task" not in loader.names()

    # Fix the skill on disk
    good_fm = {
        "name": "bad-task",
        "description": "task skill",
        "when_to_use": "t",
        "version": "1.0.0",
        "kind": "task",
        "reads": ["Overpotential"],
        "uses": ["sparql_query"],
    }
    skill_file.write_text(
        "---\n" + yaml.safe_dump(good_fm, sort_keys=False) + "---\n\n" + body,
        encoding="utf-8",
    )

    loader.reload()
    assert "bad-task" in loader.names()
    assert "bad-task" not in loader.invalid
