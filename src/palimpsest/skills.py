"""Skill loader.

Scans `skills/*/SKILL.md` once at __init__, parsing only the YAML frontmatter
so the per-skill cost of listing skills in the system prompt stays small
(~50–100 tokens each). Full body is read lazily by `load(name)` — the agent
fetches it via the `read_skill` tool when a skill is actually relevant.

Frontmatter shape (see `skills/oer-extraction/SKILL.md`):

    ---
    name: oer-extraction
    description: ...one line...
    when_to_use: ...
    version: 1.0.0
    ---

    # Body in markdown
"""

from __future__ import annotations

import warnings
from pathlib import Path

import yaml

from .skill_check import check_targets

_DELIM = "---"


def _split(text: str) -> tuple[dict, str]:
    """Split SKILL.md text into (frontmatter dict, body str).

    Raises ValueError if the opening fence is missing or the closing fence is
    not found — both are programmer errors that should be surfaced loudly.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != _DELIM:
        raise ValueError("SKILL.md missing opening --- fence")
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip() == _DELIM:
            meta = yaml.safe_load("".join(lines[1:i])) or {}
            body = "".join(lines[i + 1:])
            return meta, body
    raise ValueError("SKILL.md frontmatter not closed")


class SkillLoader:
    """Registry of skills discovered under `root/*/SKILL.md`.

    `manifest()` returns the string injected into the system prompt; `load()`
    returns the full body for one skill (lazy, re-reads the file each call).
    """

    def __init__(self, root: Path = Path("skills")) -> None:
        self.root = Path(root)
        self._skills: dict[str, dict] = {}
        # Meta of every scanned skill, valid or quarantined — lets the T69 gate
        # (`validate_skill`) report on a quarantined skill the corrector wants to fix.
        self._meta: dict[str, dict] = {}
        # Quarantined skills: name -> reason. A skill whose declared `targets:`
        # name a non-existent schema class is NOT registered (so it can't be
        # used) but does not crash the process (T69; "refuse to use, not to boot"
        # — keeps the agent alive for the future corrector layer).
        self.invalid: dict[str, str] = {}
        for skill_md in sorted(self.root.glob("*/SKILL.md")):
            meta, _ = _split(skill_md.read_text(encoding="utf-8"))
            name = meta["name"]
            self._meta[name] = meta
            targets = meta.get("targets")
            if targets:
                missing = check_targets(name, targets)
                if missing:
                    reason = f"targets unknown schema classes: {', '.join(missing)}"
                    self.invalid[name] = reason
                    warnings.warn(
                        f"skill {name!r} quarantined: {reason}", stacklevel=2
                    )
                    continue
            self._skills[name] = {"path": skill_md, "meta": meta}

    def manifest(self) -> str:
        """One-line-per-skill listing for the system prompt."""
        return "\n".join(
            f"- {s['meta']['name']}: {s['meta']['description']}"
            for s in self._skills.values()
        )

    def names(self) -> list[str]:
        """Sorted list of registered skill names — for error messages and discovery."""
        return sorted(self._skills)

    def load(self, name: str) -> str:
        """Return the body of the named SKILL.md (frontmatter stripped)."""
        if name not in self._skills:
            raise KeyError(name)
        _, body = _split(self._skills[name]["path"].read_text(encoding="utf-8"))
        return body.strip()
