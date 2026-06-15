"""T22 — schema-first extraction tool: parser output → Sonnet → Pydantic.

Pulls cached parser output (T15/T17), composes a cached system prompt (skill body
T20–T21, generated JSON schema T19, normalization overlay T20.5), calls Sonnet,
and validates the JSON items into Pydantic instances (T18/T19).

Returns ``(valid, errors)`` where ``errors`` is a list of ``(exc, raw_item)``
tuples — the agent (T23/T24) inspects ``errors`` to decide whether to re-prompt.

Provenance non-negotiable (CLAUDE.md): a Measurement subclass without an
``evidence`` dict is routed to ``errors`` here, not silently passed on as
``valid`` with ``evidence=None``. ``paper.sha256`` and ``parser_name`` are
injected from the caller args (knowable at this layer); ``page`` comes from the
LLM. Either missing → error.

T49 (C3): the ``bbox`` is NOT LLM-owned — the model emits a verbatim
``source_text`` quote, and the runtime resolves the four ``bbox_*`` corners by
matching that quote against the parser's native geometry. A measurement whose
quote matches no parser span (or whose parser has no geometry, i.e. Chandra
markdown) is routed to ``errors`` rather than carrying a fabricated bbox into the
graph. Invariant: every bbox inserted downstream is parser-native by construction.

T49 (C2): ``unit_label`` is validated against the slot's canonical unit
(``normalize.canonical_unit``); a mismatch is routed to ``errors``, never inserted.
"""

from __future__ import annotations

import copy
import inspect
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from palimpsest.normalize import build_normalization_prompt, canonical_unit, units_match
from palimpsest.providers import AnthropicProvider, DeepSeekProvider

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
_PROVIDER: AnthropicProvider | None = None  # lazy: needs DEEPSEEK_API_KEY (T50 default)
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


_BBOX_SLOTS = ("bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1")


def _schema_without_bbox(jsonschema_str: str) -> str:
    """Drop the four bbox_* slots from the Evidence definition shown to the LLM.

    The runtime resolves bbox from parser geometry (T49), so the model must not be
    asked for it. Leaving bbox in the embedded schema as `required` while the
    instructions say "don't emit bbox" is a contradictory signal; stripping it makes
    the contract coherent. This affects ONLY the prompt text — validation/store use
    the real generated schema unchanged.
    """
    schema = json.loads(jsonschema_str)
    ev = schema.get("$defs", {}).get("Evidence", {})
    for k in _BBOX_SLOTS:
        ev.get("properties", {}).pop(k, None)
    if "required" in ev:
        ev["required"] = [r for r in ev["required"] if r not in _BBOX_SLOTS]
    return json.dumps(schema, indent=2)


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
        "- Each item takes `value` (float), `unit_label` (string, the canonical "
        "unit per Normalization rules — convert before emitting), optional "
        "`condition`, and `evidence`.\n"
        "- `evidence` MUST carry `page` (int) and `source_text`: a VERBATIM quote "
        "(an exact substring) of the parsed text that states this measurement. Do "
        "NOT emit bbox coordinates, `paper.sha256`, or `parser_name` — the runtime "
        "resolves the bbox from the parser's native geometry by matching your "
        "`source_text`, and injects sha256/parser_name after parsing. Omit a "
        "measurement entirely rather than ship it without `page` + a verbatim "
        "`source_text`.\n"
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
    paper_hash" non-negotiable. ``page`` stays LLM-owned; ``bbox`` is resolved
    separately from parser geometry (see ``_resolve_bbox``), not from the LLM.

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


# --- T49: parser-native bbox resolution --------------------------------------
# Each adapter turns one parser's cached output into a flat list of
# (page:int, text:str, bbox:(x0,y0,x1,y1)) spans in the parser's NATIVE
# coordinates (no cross-parser normalization — that is T38's job, which must also
# account for docling's BOTTOMLEFT/point origin vs the others' TOPLEFT/pixel one).
# Chandra is markdown with no geometry → no adapter; its measurements route to
# errors. Page numbering: mineru/dots/paddle are 0-based list/index → +1;
# docling's prov.page_no is already 1-based.

Span = tuple[int, str, tuple[float, float, float, float]]


def _content_strings(node: Any) -> list[str]:
    """Collect every string under a ``"content"`` key, recursing dicts/lists.

    mineru nests block text as ``content`` leaves (``title_content`` →
    ``{"type": ..., "content": "..."}``, inline equations, etc.); this flattens
    one block into its visible text without dragging in ``type``/``level`` keys.
    """
    out: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "content" and isinstance(v, str):
                out.append(v)
            else:
                out.extend(_content_strings(v))
    elif isinstance(node, list):
        for item in node:
            out.extend(_content_strings(item))
    return out


def _as_bbox(seq: Any) -> tuple[float, float, float, float] | None:
    if isinstance(seq, list) and len(seq) == 4:
        return tuple(float(c) for c in seq)  # type: ignore[return-value]
    return None


def _spans_mineru(data: Any) -> list[Span]:
    spans: list[Span] = []
    for i, page in enumerate(data):
        for block in page:
            bbox = _as_bbox(block.get("bbox"))
            text = " ".join(_content_strings(block))
            if bbox and text.strip():
                spans.append((i + 1, text, bbox))
    return spans


def _spans_dots(data: Any) -> list[Span]:
    spans: list[Span] = []
    for i, page in enumerate(data.get("pages", [])):
        for item in page:
            bbox = _as_bbox(item.get("bbox"))
            text = item.get("text", "")
            if bbox and isinstance(text, str) and text.strip():
                spans.append((i + 1, text, bbox))
    return spans


def _spans_paddle(data: Any) -> list[Span]:
    spans: list[Span] = []
    for page in data.get("pages", []):
        res = page.get("res", {})
        idx = res.get("page_index")
        page_no = idx + 1 if isinstance(idx, int) else None
        if page_no is None:
            continue
        for block in res.get("parsing_res_list", []):
            bbox = _as_bbox(block.get("block_bbox"))
            text = block.get("block_content", "")
            if bbox and isinstance(text, str) and text.strip():
                spans.append((page_no, text, bbox))
    return spans


def _spans_docling(data: Any) -> list[Span]:
    spans: list[Span] = []
    for t in data.get("texts", []):
        text = t.get("text") or t.get("orig") or ""
        if not (isinstance(text, str) and text.strip()):
            continue
        for prov in t.get("prov", []):
            page_no = prov.get("page_no")
            b = prov.get("bbox", {})
            if isinstance(page_no, int) and all(k in b for k in ("l", "t", "r", "b")):
                spans.append((page_no, text,
                              (float(b["l"]), float(b["t"]), float(b["r"]), float(b["b"]))))
    return spans


_GEOMETRY = {
    "mineru": _spans_mineru,
    "dots": _spans_dots,
    "paddle": _spans_paddle,
    "docling": _spans_docling,
}


def _load_spans(parser_name: str, parser_text: str) -> list[Span]:
    """Parse cached parser output into spans; ``[]`` for no-geometry parsers.

    Chandra emits markdown (no geometry) and an unknown/unparseable parser also
    yields ``[]`` — both cases leave every measurement's bbox unresolved, so the
    extract loop routes them to ``errors`` (never a fabricated bbox).
    """
    fn = _GEOMETRY.get(parser_name)
    if fn is None:
        return []
    try:
        data = json.loads(parser_text)
    except json.JSONDecodeError:
        return []
    return fn(data)


def _norm(s: str) -> str:
    # Remove ALL whitespace (not just collapse) and lowercase. Parsers pad inline
    # equations and tokens with spaces the LLM's continuous quote doesn't have
    # (mineru: "Ir- Co_{3}O_{4}" vs the quote's "Ir-Co_{3}O_{4}"); dropping
    # whitespace entirely makes substring matching robust to that.
    return re.sub(r"\s+", "", s).lower()


# Minimum normalized length for a span to match by being *contained in* the quote
# (the multi-span union direction). Without it, trivially short parser spans —
# docling emits single-char spans like "h", mineru emits "Materials" — are a
# substring of almost any quote and would pollute the union bbox, stretching it
# to wherever that fragment sits on the page. The other direction (quote ⊆ span)
# is unaffected: the quote is the long string there.
_MIN_SPAN_MATCH_CHARS = 4


def _bbox_area(b: tuple[float, float, float, float]) -> float:
    return abs((b[2] - b[0]) * (b[3] - b[1]))


def _resolve_bbox(items: list[dict], spans: list[Span]) -> None:
    """Replace each evidence's bbox with the parser-native one matching its quote.

    Mutates each item's ``evidence`` in place: the LLM-emitted ``bbox_*`` (if any)
    are dropped, then resolved from the spans on the stated ``page``:

    1. If any span fully CONTAINS the quote, use the TIGHTEST such span (smallest
       area). This is the common case (a paragraph/line span holding the quote)
       and gives the most precise bbox.
    2. Otherwise the quote is split across spans — union the span chunks that are
       part of it (``ntext in snippet``), guarded by ``_MIN_SPAN_MATCH_CHARS``.

    Doing (1) before (2) avoids unioning a correct containing span with an
    unrelated short fragment elsewhere on the page (which inflates the bbox — the
    opposite of what T38 needs). No match (or no ``source_text`` / no spans) →
    bbox left UNSET, so the extract loop sends the measurement to ``errors``.
    """
    by_page: dict[Any, list[tuple[str, tuple[float, float, float, float]]]] = {}
    for page_no, text, bbox in spans:
        by_page.setdefault(page_no, []).append((_norm(text), bbox))

    for item in items:
        ev = item.get("evidence")
        if not isinstance(ev, dict):
            continue
        for k in ("bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1"):
            ev.pop(k, None)  # runtime owns bbox now; discard whatever the LLM sent
        src = ev.get("source_text")
        if not (isinstance(src, str) and src.strip()):
            continue
        snippet = _norm(src)
        # Spans are keyed by int page; tolerate a stringified page from the LLM
        # so a "3" vs 3 mismatch isn't a spurious resolution failure.
        try:
            page = int(ev.get("page"))
        except (TypeError, ValueError):
            continue
        page_spans = [(ntext, bbox) for ntext, bbox in by_page.get(page, []) if ntext]
        # (1) tightest single span that fully contains the quote.
        containing = [bbox for ntext, bbox in page_spans if snippet in ntext]
        if containing:
            matched = [min(containing, key=_bbox_area)]
        else:
            # (2) quote split across spans: union the chunks that are part of it.
            matched = [
                bbox for ntext, bbox in page_spans
                if len(ntext) >= _MIN_SPAN_MATCH_CHARS and ntext in snippet
            ]
        if not matched:
            continue
        ev["bbox_x0"] = min(b[0] for b in matched)
        ev["bbox_y0"] = min(b[1] for b in matched)
        ev["bbox_x1"] = max(b[2] for b in matched)
        ev["bbox_y1"] = max(b[3] for b in matched)


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
    jsonschema_str = _schema_without_bbox(_JSONSCHEMA_PATH.read_text(encoding="utf-8"))
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
            _PROVIDER = DeepSeekProvider()  # T50: DeepSeek is the default LLM
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
        cost_meter.record_llm(
            provider.name,
            _cost_eur(resp.usage, getattr(provider, "prices", None)),
            detail="extract",
        )

    items = _parse_response(resp.text)
    # Caller owns paper.sha256 and parser_name; overwrite whatever the LLM
    # emitted there. Done BEFORE the raw snapshot so failed-item replay
    # reflects what _instantiate actually saw.
    _inject_provenance(items, paper_sha, parser_name)
    # T49 (C3): resolve each bbox from the parser's native geometry by matching
    # the LLM's verbatim source_text quote. Done BEFORE the raw snapshot so a
    # failed item's replay shows the resolved (or unresolved) bbox state.
    _resolve_bbox(items, _load_spans(parser_name, parser_text))
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
        if type_name in _MEASUREMENT_NAMES:
            ev = item.get("evidence")
            if not isinstance(ev, dict):
                errors.append((ValueError(f"missing evidence for {type_name}"), raw))
                continue
            # T49 (C3): no parser-native bbox matched the quote (no match, no
            # source_text, or a no-geometry parser like Chandra). Refuse rather
            # than carry a fabricated bbox into the graph.
            if not all(k in ev for k in ("bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1")):
                errors.append((
                    ValueError(
                        f"no parser-native bbox for {type_name}; "
                        f"source_text={ev.get('source_text')!r} did not match a "
                        f"{parser_name} span on page {ev.get('page')}"
                    ),
                    raw,
                ))
                continue
        try:
            inst = _instantiate(item)
        except (ValidationError, KeyError, TypeError) as exc:
            errors.append((exc, raw))
            continue
        # T49 (C2): reject a unit_label that disagrees with the slot's canonical
        # unit. Comparison is by unit signature (normalize.units_match), so a
        # correct unit in paper-faithful spelling (`s⁻¹`, `A g⁻¹_Ir`) passes while
        # a genuine error (`V` for an mV slot) still fails. Only Measurement
        # subclasses carry unit_label; canonical_unit returns None when untracked.
        if type_name in _MEASUREMENT_NAMES:
            canon = canonical_unit(type_name)
            if canon is not None and not units_match(inst.unit_label, canon):
                errors.append((
                    ValueError(
                        f"unit_label {inst.unit_label!r} != canonical {canon!r} "
                        f"for {type_name}"
                    ),
                    raw,
                ))
                continue
        valid.append(inst)
    return valid, errors
