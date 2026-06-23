"""Skill loader.

Scans `skills/**/SKILL.md` recursively once at __init__, parsing only the YAML
frontmatter so the per-skill cost of listing skills in the system prompt stays
small (~50–100 tokens each). Full body is read lazily by `load(name)` — the
agent fetches it via the `read_skill` tool when a skill is actually relevant.

Layout convention:
  skills/domain/   — extraction skills (e.g. oer-extraction, pemwe-anode)
  skills/general/  — task skills (agent-level procedures)

Frontmatter shape (extraction skill, see `skills/domain/oer-extraction/SKILL.md`):

    ---
    name: oer-extraction
    description: ...one line...
    when_to_use: ...
    version: 1.0.0
    targets: [Overpotential, TafelSlope, ...]   # schema Measurement classes
    ---

    # Body in markdown

Task skills additionally carry `kind: task`, `reads: [...]` (schema classes
they query), and `uses: [...]` (registered tool names they invoke).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import yaml

from .skill_check import check_reads, check_targets

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
    """Registry of skills discovered under `root/**/SKILL.md`.

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
        # Invariant: no accessor (manifest/names/load/skill_dir) may run at IMPORT
        # time. `_LOADER` is constructed in read_skill.py while tools/__init__.py is
        # still importing tool modules, so TOOLS is incomplete then; finalizing early
        # would run the uses-gate against a half-built registry and spuriously
        # quarantine task skills whose `uses:` name a not-yet-imported tool.
        # Guarded by test_loader_not_finalized_at_import.
        self._finalized = False
        self._scan()

    def _scan(self) -> None:
        """Scan skills/ from disk and populate _skills, _meta, invalid."""
        for skill_md in sorted(self.root.glob("**/SKILL.md")):
            meta, _ = _split(skill_md.read_text(encoding="utf-8"))
            name = meta["name"]
            self._meta[name] = meta
            kind = meta.get("kind", "extraction")
            if kind == "task":
                reads = meta.get("reads") or []
                missing = check_reads(name, reads)
                if missing:
                    reason = f"reads unknown schema classes: {', '.join(missing)}"
                    self.invalid[name] = reason
                    warnings.warn(f"skill {name!r} quarantined: {reason}", stacklevel=2)
                    continue
            else:
                targets = meta.get("targets")
                if targets:
                    missing = check_targets(name, targets)
                    if missing:
                        reason = f"targets unknown schema classes: {', '.join(missing)}"
                        self.invalid[name] = reason
                        warnings.warn(f"skill {name!r} quarantined: {reason}", stacklevel=2)
                        continue
            self._skills[name] = {"path": skill_md, "meta": meta, "kind": kind}

    def reload(self) -> None:
        """Re-scan skills/ from disk so a skill authored after construction becomes
        visible. Resets the lazy uses-gate; the next accessor re-finalizes against
        the now-complete TOOLS registry. Does NOT clear skill_check's @cache'd schema
        helpers (the schema is unchanged when a SKILL.md is authored)."""
        self._skills.clear()
        self._meta.clear()
        self.invalid.clear()
        self._finalized = False
        self._scan()

    def _ensure_finalized(self) -> None:
        """Run the deferred `uses:` gate once, when the tool registry is complete.

        The loader is constructed during early tool import (before most tools
        register), so a task skill's `uses:` cannot be checked at __init__.
        Every accessor calls this first; it runs at most once.

        Calling this at import time (before tools/__init__.py finishes) would
        import a half-built TOOLS registry and spuriously quarantine task skills
        whose `uses:` name a not-yet-imported tool. See the invariant comment
        near `self._finalized = False` in __init__ and the guard test
        test_loader_not_finalized_at_import.
        """
        if self._finalized:
            return
        self._finalized = True
        from .tools import TOOLS  # lazy: avoid the import cycle; complete at runtime
        for name in list(self._skills):
            if self._skills[name]["kind"] != "task":
                continue
            uses = self._skills[name]["meta"].get("uses") or []
            missing = [u for u in uses if u not in TOOLS]
            if missing:
                reason = f"uses unregistered tools: {', '.join(missing)}"
                self.invalid[name] = reason
                warnings.warn(f"skill {name!r} quarantined: {reason}", stacklevel=2)
                del self._skills[name]

    def manifest(self) -> str:
        """One-line-per-skill listing for the system prompt, grouped by kind."""
        self._ensure_finalized()
        domain = [s for s in self._skills.values() if s["kind"] != "task"]
        task = [s for s in self._skills.values() if s["kind"] == "task"]

        def _lines(group):
            return [f"- {s['meta']['name']}: {s['meta']['description']}" for s in group]

        out: list[str] = []
        if domain:
            out.append("**Domain skills** (extraction — load before extracting in that domain):")
            out += _lines(domain)
        if task:
            if out:
                out.append("")
            out.append("**General skills** (analysis/reporting tasks):")
            out += _lines(task)
        return "\n".join(out)

    def names(self) -> list[str]:
        """Sorted list of registered skill names — for error messages and discovery."""
        self._ensure_finalized()
        return sorted(self._skills)

    def load(self, name: str) -> str:
        """Return the body of the named SKILL.md (frontmatter stripped)."""
        self._ensure_finalized()
        if name not in self._skills:
            raise KeyError(name)
        _, body = _split(self._skills[name]["path"].read_text(encoding="utf-8"))
        return body.strip()

    def skill_dir(self, name: str) -> Path:
        """Directory containing the named skill's SKILL.md (for normalization etc.).

        Source of truth for a skill's on-disk location, so callers never
        reconstruct `Path("skills") / name` (which breaks when skills move).
        """
        self._ensure_finalized()
        if name not in self._skills:
            raise KeyError(name)
        return self._skills[name]["path"].parent
