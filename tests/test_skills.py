"""T21 — SkillLoader contract tests.

Card asks for two assertions; we add a third for the KeyError contract that
`read_skill`'s tool wrapper depends on.
"""

from __future__ import annotations

import pytest

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
