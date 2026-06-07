"""T22 — schema-first extraction tool: parser output → Sonnet → Pydantic.

Pulls cached parser output (T15/T17), composes a cached system prompt (skill body
T20–T21, generated JSON schema T19, normalization overlay T20.5), calls Sonnet,
and validates the JSON items into Pydantic instances (T18/T19).

Returns ``(valid, errors)`` where ``errors`` is a list of ``(exc, raw_item)``
tuples — the agent (T23/T24) inspects ``errors`` to decide whether to re-prompt.

Provenance non-negotiable (CLAUDE.md): a Measurement subclass without an
``evidence`` dict is routed to ``errors`` here, not silently passed on as
``valid`` with ``evidence=None``. ``paper.sha256`` and ``parser_name`` are
injected from the caller args (knowable at this layer); ``page`` and ``bbox``
must come from the parsed content (LLM-owned). Either side missing → error.
"""

from __future__ import annotations

import copy
import inspect
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from palimpsest.normalize import build_normalization_prompt
from palimpsest.providers import AnthropicProvider

from schema.generated import pydantic as _schema  # PEP 420 namespace pkg

from . import register
# Reuse read_skill's loader rather than constructing our own — Python's import
# machinery loads read_skill on demand here, so both tools share one
# process-wide SkillLoader instance and skip a duplicate `skills/` scan.
from .read_skill import _LOADER

# `palimpsest.cache` and `palimpsest.agent` are imported lazily inside extract()
# below — both transitively re-import `palimpsest.tools`, so importing them at
# module load time would deadlock the tools-package init that triggered this
# module's own load (`tools/__init__.py` -> extract -> cache -> tools).

# Module-level singletons. Tests override via kwargs; production calls reuse them
# so the class-map introspection happens once per process.
_PROVIDER: AnthropicProvider | None = None  # lazy: needs ANTHROPIC_API_KEY
_JSONSCHEMA_PATH = Path("schema/generated/jsonschema.json")


def _build_class_map() -> dict[str, type[BaseModel]]:
    """Map class name → Pydantic class for everything the LLM may emit.

    Excludes:
    - the abstract ``Measurement`` base (LLM must pick a subclass);
    - LinkML support classes (``ConfiguredBaseModel``, ``LinkMLMeta``);
    - pydantic re-exports (``BaseModel``, ``RootModel``) — ``inspect.getmembers``
      surfaces them because the generated module does ``from pydantic import
      BaseModel, RootModel``, and instantiating them via ``BaseModel(**item)``
      raises ``PydanticUserError`` (not ``ValidationError``), which would kill
      the batch. Filtering by ``__module__`` is the canonical fix.

    Keyed by ``cls.__name__`` so the response's ``type`` discriminator maps
    directly.
    """
    skip = {"ConfiguredBaseModel", "LinkMLMeta", "Measurement"}
    out: dict[str, type[BaseModel]] = {}
    for name, obj in inspect.getmembers(_schema, inspect.isclass):
        if name in skip:
            continue
        if obj.__module__ != _schema.__name__:
            continue
        if not issubclass(obj, BaseModel):
            continue
        out[name] = obj
    return out


_CLASS_MAP = _build_class_map()
_MEASUREMENT_NAMES = frozenset(
    n for n, c in _CLASS_MAP.items() if issubclass(c, _schema.Measurement)
)


def _build_system_prompt(skill_body: str, jsonschema_str: str, norm: str) -> str:
    """Compose the cached system block (~7K tokens for OER + full schema)."""
    # Advertise only the concrete Measurement subclasses as valid `type` values.
    # _CLASS_MAP also holds Evidence/Paper/Catalyst/etc. for _instantiate's use,
    # but those are not top-level emissions — the output contract is one item per
    # measurement, each with an embedded Evidence block.
    type_list = ", ".join(sorted(_MEASUREMENT_NAMES))
    return (
        "You are palimpsest's extraction agent. Given parsed text from an OER "
        "research paper, return one JSON object listing every reported "
        "measurement and its provenance.\n\n"
        "## Skill\n\n"
        + skill_body
        + "\n\n"
        + norm
        + "\n## Schema\n\n"
        "The Pydantic classes you may instantiate are defined by this JSON "
        "schema:\n\n```json\n"
        + jsonschema_str
        + "\n```\n\n## Output contract\n\n"
        "Return EXACTLY ONE JSON object of the form:\n\n"
        '```\n{"items": [\n'
        '  {"type": "<MeasurementSubclass>", "<slot>": <value>, ..., "evidence": {...}},\n'
        '  ...\n]}\n```\n\n'
        f"- `type` must be one of: {type_list}.\n"
        "- Do NOT emit `type: Measurement` — it is the abstract base; always "
        "pick a concrete subclass.\n"
        "- Each item takes `value` (float), `unit_label` (string, canonical "
        "unit per Normalization rules), optional `condition`, and `evidence`.\n"
        "- `evidence` MUST carry `page` (int) and `bbox` (exactly 4 floats) "
        "located in the parsed content. Do NOT emit `paper.sha256` or "
        "`parser_name` — the runtime injects both after parsing. Omit a "
        "measurement entirely rather than ship it without page+bbox.\n"
        "- One item per (variable, conditions) tuple.\n"
        "- Return JSON only — no prose, no commentary, no markdown fence around "
        "the outer object."
    )


_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_response(text: str) -> list[dict]:
    """Pull ``items`` out of the response.

    Tries strict JSON first; falls back to a fenced ```json``` block; raises
    ``ValueError`` if neither yields a dict with a list-typed ``items`` key.
    The fallback exists because models occasionally wrap JSON in a fence
    despite the contract; raising on missing/malformed ``items`` is per
    CLAUDE.md §1 (loud failure). Returning a non-list to the caller would
    crash the iteration loop with ``AttributeError``, so we reject it here.
    """
    candidates: list[str] = [text]
    fence = _FENCED.search(text)
    if fence:
        candidates.append(fence.group(1))
    for cand in candidates:
        try:
            body = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(body, dict) and isinstance(body.get("items"), list):
            return body["items"]
    raise ValueError(
        f"LLM response not parseable as {{\"items\": [...]}}; head: {text[:200]!r}"
    )


def _inject_provenance(items: list[dict], paper_sha: str, parser_name: str) -> None:
    """Overwrite the provenance fields the caller owns, not the LLM.

    ``paper.sha256`` and ``parser_name`` are knowable at the tool layer (T07
    hash + caller's parser arg); letting the LLM emit them invites hallucinated
    hashes that would silently violate CLAUDE.md's "every triple carries
    paper_hash" non-negotiable. ``page`` and ``bbox`` stay LLM-owned because
    they come from the parsed content.

    Mutates each item's ``evidence`` block in place. An item without an
    ``evidence`` dict at all is left alone here — the calling loop in
    ``extract()`` catches missing-evidence on Measurement subclasses and
    routes the item to ``errors`` so the agent can re-prompt.
    """
    for item in items:
        ev = item.get("evidence")
        if not isinstance(ev, dict):
            continue
        ev["parser_name"] = parser_name
        paper = ev.get("paper")
        if isinstance(paper, dict):
            paper["sha256"] = paper_sha
        else:
            ev["paper"] = {"sha256": paper_sha}


def _instantiate(item: dict) -> BaseModel:
    """Pop the ``type`` discriminator and build the matching Pydantic class.

    Raises ``KeyError(type_name)`` for unknown classes (caller routes to errors);
    propagates ``pydantic.ValidationError`` for shape violations.
    """
    type_name = item.pop("type", None)
    if type_name not in _CLASS_MAP:
        raise KeyError(type_name)
    cls = _CLASS_MAP[type_name]
    return cls(**item)


@register("extract", {
    "description": "Schema-first extraction: cached parser output -> Sonnet -> Pydantic instances.",
    "input_schema": {
        "type": "object",
        "properties": {
            "paper_sha": {"type": "string"},
            "parser_name": {"type": "string"},
            "skill_name": {"type": "string"},
        },
        "required": ["paper_sha"],
    },
})
def extract(
    paper_sha: str,
    parser_name: str = "mineru",
    skill_name: str = "oer-extraction",
    *,
    cost_meter: Any = None,
    provider: Any = None,
    cache: Any = None,
) -> tuple[list[BaseModel], list[tuple[Exception, dict]]]:
    """Run one extraction over one cached parser output.

    The ``provider`` and ``cache`` kwargs exist for test injection; ``cost_meter``
    is optional so direct calls (the live snippet) can keep budget tracking
    honest without forcing the tool to construct a meter when none is wired.
    """
    if cache is None:
        from palimpsest.cache import ParserCache  # lazy: break import cycle
        cache = ParserCache()
    parser_path = cache.get_output(paper_sha, parser_name)
    if parser_path is None:
        raise FileNotFoundError(
            f"no cached output for {paper_sha}/{parser_name}; run T16 first"
        )
    parser_text = parser_path.read_text(encoding="utf-8")

    try:
        skill_body = _LOADER.load(skill_name)
    except KeyError:
        # Wrap the bare KeyError so the agent's _dispatch surfaces a friendly,
        # re-promptable message (mirrors read_skill.py's fallback format).
        avail = ", ".join(_LOADER.names()) or "(none)"
        raise ValueError(f"unknown skill: {skill_name!r}. Available: {avail}") from None
    norm = build_normalization_prompt([Path("skills") / skill_name])
    jsonschema_str = _JSONSCHEMA_PATH.read_text(encoding="utf-8")
    system = _build_system_prompt(skill_body, jsonschema_str, norm)

    messages = [
        {
            "role": "user",
            "content": f"Parser output:\n\n{parser_text}\n\nReturn the JSON now.",
        }
    ]

    global _PROVIDER
    if provider is None:
        if _PROVIDER is None:
            _PROVIDER = AnthropicProvider()
        provider = _PROVIDER
    resp = provider.complete(
        system=system,
        messages=messages,
        tools=None,
        cache_breakpoints=["system"],
    )
    if cost_meter is not None:
        # `_cost_eur` is the canonical Sonnet pricing table (agent.py T06);
        # reuse it so a future price tweak lands in one place. Lazy import
        # for the same import-cycle reason as ParserCache above.
        from palimpsest.agent import _cost_eur
        cost_meter.record_llm(provider.name, _cost_eur(resp.usage), detail="extract")

    items = _parse_response(resp.text)
    # Caller owns paper.sha256 and parser_name; overwrite whatever the LLM
    # emitted there. Done BEFORE the raw snapshot so failed-item replay
    # reflects what _instantiate actually saw.
    _inject_provenance(items, paper_sha, parser_name)
    valid: list[BaseModel] = []
    errors: list[tuple[Exception, dict]] = []
    for item in items:
        if not isinstance(item, dict):
            errors.append((TypeError(f"item is {type(item).__name__}, expected dict"), {"raw": item}))
            continue
        # Deep-copy so error-replay shows the exact state _instantiate saw,
        # not a snapshot whose nested `evidence` dict still aliases the live
        # one (a shallow copy is safe today but fragile if any future fix
        # mutates nested keys).
        raw = copy.deepcopy(item)
        # Provenance non-negotiable (CLAUDE.md): a Measurement subclass MUST
        # carry an evidence dict so the (paper_hash, parser, page, bbox) tuple
        # is recoverable downstream. Catching this here lets the agent re-prompt
        # cheaply before T24's expensive insertion gate.
        type_name = item.get("type")
        if type_name in _MEASUREMENT_NAMES and not isinstance(item.get("evidence"), dict):
            errors.append((ValueError(f"missing evidence for {type_name}"), raw))
            continue
        try:
            valid.append(_instantiate(item))
        except (ValidationError, KeyError, TypeError) as exc:
            errors.append((exc, raw))
    return valid, errors
