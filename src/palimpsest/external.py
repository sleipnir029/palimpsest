"""Bring-your-own-agent extraction (no API key needed).

A coding agent (Claude Code, Codex, OpenCode, ...) opened in this repo can play the
extraction model: `render_prompt` returns the exact prompt `extract()` would send
(skill + schema + numbered text spans), the agent writes its JSON answer to a file,
and `ingest` feeds that answer through the normal pipeline. The checks stay in code:
span resolution, digits-in-span, units, schema, SHACL, and provenance attached by
code from the cited span ids. palimpsest makes no paid call, so nothing is metered.
"""

from __future__ import annotations

from pathlib import Path

from .cache import ParserCache
from .cost import CostMeter
from .pipeline import run_paper
from .providers.anthropic import LLMResponse
from .runs import ExtractionRunLog
from .store import RDFStore
from .tools.extract import extract
from .tools.read_paper import read_paper

EXTERNAL_MODEL = "external-agent"
_ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0}


class _Capture:
    """Records the prompt extract() sends; answers with no measurements."""

    name = EXTERNAL_MODEL

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system, messages, **_kw):
        self.calls.append((system, messages[0]["content"]))
        return LLMResponse(text="[]", tool_calls=[], usage=dict(_ZERO_USAGE), raw={})


class _Replay:
    """Returns the coding agent's saved answer as the model's reply (one call only)."""

    name = EXTERNAL_MODEL

    def __init__(self, text: str) -> None:
        self.text = text
        self.used = False

    def complete(self, **_kw):
        if self.used:
            raise RuntimeError("paper needs several prompts; external mode supports one")
        self.used = True
        return LLMResponse(text=self.text, tool_calls=[], usage=dict(_ZERO_USAGE), raw={})


def render_prompt(pdf: str | Path, parser_name: str = "docling",
                  skill_name: str = "oer-extraction") -> str:
    """The exact extraction prompt for a cached parse of `pdf`, as one markdown text."""
    sha = read_paper(str(pdf))["sha256"]
    cap = _Capture()
    extract(sha, parser_name, skill_name, provider=cap)
    if len(cap.calls) != 1:
        raise RuntimeError(
            f"this paper needs {len(cap.calls)} prompts (too long for one); "
            "use an API-key model instead (see README)")
    system, user = cap.calls[0]
    return (
        "# palimpsest extraction prompt\n\n"
        "Act as the extraction model. Follow the system instructions, read the user "
        "message, and save ONLY the JSON answer (no prose, no code fences) to a file. "
        "Then run `pixi run python -m palimpsest ingest <pdf> --response <file>`.\n\n"
        f"## System\n\n{system}\n\n## User\n\n{user}\n"
    )


def ingest(pdf: str | Path, response: str | Path, parser_name: str = "docling",
           skill_name: str = "oer-extraction", *, store: RDFStore | None = None,
           db_path: str = "palimpsest.db") -> dict:
    """Run the agent's saved answer through the pipeline (gates + provenance insert)."""
    return run_paper(
        Path(pdf), parser_name, skill_name,
        store=store if store is not None else RDFStore("store"),
        cache=ParserCache(db_path),
        cost_meter=CostMeter(db_path),
        run_log=ExtractionRunLog(db_path),
        provider=_Replay(Path(response).read_text(encoding="utf-8")),
        extraction_model=EXTERNAL_MODEL,
    )
