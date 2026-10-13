"""T22/T51 — schema-first extraction: parser output → LLM → Pydantic.

Pulls cached parser output (T15/T17), projects it to numbered text spans, and
runs ONE LLM call over the full projection (per-page batching only as a fallback
for projections too large to fit): the model is shown the numbered spans and
returns measurements, each citing the span id(s) that state it. The runtime
maps cited ids → bbox / page / source_text directly (no fuzzy matching).

Returns ``(valid, errors)`` where ``errors`` is a list of ``(exc, raw_item)``
tuples — the agent (T23/T24) inspects ``errors`` to decide whether to re-prompt.

Design (T51, supersedes the T49 fuzzy matcher):
- **Span projection (S2):** each parser's native geometry → ``(page, text, bbox)``
  spans via the per-parser adapters. The LLM sees ``[id] <text>`` lines, never the
  raw JSON — so the input is small and parser-agnostic (any LLM, any size).
- **ID citation (S3):** the model returns ``evidence: {"spans": [id, ...]}``; the
  runtime resolves ids → union bbox, page, concatenated ``source_text``. No quote
  matching, so LaTeX/whitespace differences and equation-sourced values can't break
  resolution. Invalid/empty ids → routed to ``errors`` (provenance non-negotiable).
- **Per-page (S4) + no-strip:** one call per page keeps each call tiny, so span text
  is shown and stored VERBATIM — we never strip LaTeX/subscripts (``_{Ir}``,
  ``^{-1}``, ``Co_{3}O_{4}``) that carry chemical/unit meaning.

``paper.sha256`` + ``parser_name`` are injected by the runtime (not LLM-owned).
``unit_label`` is validated against the canonical unit (``normalize.units_match``);
mismatches route to ``errors`` (C2). Chandra has no geometry → no spans → nothing
extractable.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from palimpsest.normalize import (
    build_normalization_prompt, canonical_unit, check_milli_value, magnitude_ok,
    units_match,
)

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
_PROVIDER_CACHE: dict[str, Any] = {}  # extraction_model name → provider instance (lazy)
_JSONSCHEMA_PATH = Path("schema/generated/jsonschema.json")


def _resolve_extraction_provider(db_path: str = "palimpsest.db") -> Any:
    """Build the extraction provider named by the ``extraction_model`` setting.

    Independent of the agent's orchestration model (app phase): extraction may run
    on any provider, including OpenAI-compat ones (Gemini) that can't drive the
    agent loop. Cached by name so the class-map introspection happens once.
    """
    from palimpsest.config import get_setting
    from palimpsest.providers import build_provider

    name = get_setting("extraction_model", "deepseek", db_path=db_path) or "deepseek"
    if name not in _PROVIDER_CACHE:
        _PROVIDER_CACHE[name] = build_provider(name)
    return _PROVIDER_CACHE[name]


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

# Evidence fields the RUNTIME fills (from cited spans + caller args), so the LLM
# must not be asked for them. They're stripped from the schema shown to the model;
# the prose contract tells it to emit only `evidence: {"spans": [id, ...]}`.
_EVIDENCE_RUNTIME_SLOTS = (
    "paper", "page", "bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1",
    "source_text", "parser_name",
)


def _schema_for_prompt(jsonschema_str: str) -> str:
    """Strip the runtime-filled Evidence fields from the schema shown to the LLM.

    The model cites span ids; the runtime derives page/bbox/source_text/parser/paper
    from those spans. Showing Evidence's real (required) fields would invite the model
    to emit them — a contradictory contract. This affects ONLY the prompt text;
    validation/store use the real generated schema unchanged.
    """
    schema = json.loads(jsonschema_str)
    ev = schema.get("$defs", {}).get("Evidence", {})
    for k in _EVIDENCE_RUNTIME_SLOTS:
        ev.get("properties", {}).pop(k, None)
    ev["required"] = []
    return json.dumps(schema, indent=2)


def _build_system_prompt(skill_body: str, jsonschema_str: str, norm: str) -> str:
    """Compose the cached system block (~7K tokens for OER + full schema)."""
    type_list = ", ".join(sorted(_MEASUREMENT_NAMES))
    return (
        "You are palimpsest's extraction agent. You are given the NUMBERED text "
        "spans of ONE page of an OER research paper. Return every reported "
        "measurement that those spans state, citing the span id(s) for each.\n\n"
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
        '  {"type": "<MeasurementSubclass>", "value": <float>, "unit_label": "<unit>",\n'
        '   "confidence": <float 0-1>, "condition": {...}, "evidence": {"spans": [<id>, ...]}},\n'
        '  ...\n]}\n```\n\n'
        f"- `type` must be one of: {type_list}. Never emit `type: Measurement` "
        "(it is the abstract base).\n"
        "- `value` (float) + `unit_label` (string, the canonical unit per the "
        "Normalization rules — convert before emitting). `condition` is optional.\n"
        "- `confidence` (float 0-1, optional): your self-assessed certainty that "
        "this value/unit is correctly extracted from the cited span(s). Use ~0.9+ "
        "when the span states it explicitly, lower when inferred or ambiguous. Omit "
        "if you cannot judge.\n"
        "- `evidence.spans` MUST list the id(s) of the span(s) on THIS page that "
        "state the measurement (the span(s) containing the value). Cite the "
        "smallest set that covers it — usually one id. Do NOT invent ids, and do "
        "NOT emit page/bbox/source_text/paper/parser_name; the runtime fills those "
        "from the spans you cite.\n"
        "- Only emit a measurement if a span on this page actually states it. If "
        "no measurement is stated on this page, return `{\"items\": []}`.\n"
        "- One item per (variable, conditions) tuple.\n"
        "- Return JSON only — no prose, no commentary, no markdown fence around "
        "the outer object."
    )


_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_response(text: str) -> list[dict]:
    """Pull ``items`` out of the response.

    Tries strict JSON first; falls back to a fenced ```json``` block; raises
    ``ValueError`` if neither yields a dict with a list-typed ``items`` key.
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


# --- span projection: parser-native geometry → (page, text, bbox) -------------
# Each adapter turns one parser's cached output into spans in the parser's NATIVE
# coordinates (no cross-parser normalization — that is T38's job). Span text is
# kept VERBATIM (no LaTeX/whitespace stripping). Chandra is markdown with no
# geometry → no adapter → no spans. Page numbering: mineru/dots/paddle are 0-based
# list/index → +1; docling's prov.page_no is already 1-based.

Span = tuple[int, str, tuple[float, float, float, float]]

# Keys whose string values are visible block text. mineru nests running text under
# "content" and equation LaTeX under "math_content"; both must be projected or the
# values they carry become uncitable.
_TEXT_KEYS = {"content", "math_content"}


def _content_strings(node: Any) -> list[str]:
    """Collect every string under a text-bearing key, recursing dicts/lists."""
    out: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _TEXT_KEYS and isinstance(v, str):
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


def _docling_bbox(b: Any) -> tuple[float, float, float, float] | None:
    if isinstance(b, dict) and all(k in b for k in ("l", "t", "r", "b")):
        # docling uses BOTTOMLEFT origin (y increases upward), so t > b.
        # Normalise to top-left origin (y0 < y1) with min/max.
        y0, y1 = min(float(b["t"]), float(b["b"])), max(float(b["t"]), float(b["b"]))
        return (float(b["l"]), y0, float(b["r"]), y1)
    return None


def _spans_docling(data: Any) -> list[Span]:
    spans: list[Span] = []
    for t in data.get("texts", []):
        text = t.get("text") or t.get("orig") or ""
        if not (isinstance(text, str) and text.strip()):
            continue
        for prov in t.get("prov", []):
            bbox = _docling_bbox(prov.get("bbox"))
            page_no = prov.get("page_no")
            if isinstance(page_no, int) and bbox:
                spans.append((page_no, text, bbox))
    # Tables live in a separate array, not in `texts`. Project their cell text so
    # table-sourced values stay citable. (Verified against a synthetic structure;
    # the sample corpus has no tables — see PROGRESS.)
    for tbl in data.get("tables", []):
        cell_text = " ".join(_docling_table_text(tbl.get("data")))
        if not cell_text.strip():
            continue
        for prov in tbl.get("prov", []):
            bbox = _docling_bbox(prov.get("bbox"))
            page_no = prov.get("page_no")
            if isinstance(page_no, int) and bbox:
                spans.append((page_no, cell_text, bbox))
    return spans


def _docling_table_text(node: Any) -> list[str]:
    """Collect cell ``text`` strings from a docling table's ``data`` block."""
    out: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "text" and isinstance(v, str):
                out.append(v)
            else:
                out.extend(_docling_table_text(v))
    elif isinstance(node, list):
        for item in node:
            out.extend(_docling_table_text(item))
    return out


_GEOMETRY = {
    "mineru": _spans_mineru,
    "dots": _spans_dots,
    "paddle": _spans_paddle,
    "docling": _spans_docling,
}


def _load_spans(parser_name: str, parser_text: str) -> list[Span]:
    """Parse cached parser output into spans; ``[]`` for no-geometry parsers.

    Chandra emits markdown (no geometry) and an unknown/unparseable parser also
    yields ``[]`` — nothing citable, so no measurements are extracted.
    """
    fn = _GEOMETRY.get(parser_name)
    if fn is None:
        return []
    try:
        data = json.loads(parser_text)
    except json.JSONDecodeError:
        return []
    return fn(data)


# One call over the full projection unless its text exceeds this (~chars/4 tokens),
# in which case we fall back to per-page batching. A single paper's projection is
# ~20-25K tokens, so this only triggers for very large inputs (generality safety net).
_MAX_PROJECTION_TOKENS = 120_000


def _render_projection(spans: list[Span], ids: list[int] | None = None) -> str:
    """Numbered span listing with GLOBAL ids. ``ids`` selects a subset (a page batch)."""
    sel = range(len(spans)) if ids is None else ids
    lines = ["Numbered text spans (cite the [id] of the span stating each measurement):", ""]
    for i in sel:
        page, text, _bbox = spans[i]
        lines.append(f"[{i}] (p{page}) {text}")
    return "\n".join(lines)


# Condition/Electrolyte slots typed `float` in the schema. The LLM intermittently
# emits these as unit-bearing strings ("10 mA/cm2", "1.53 V"); left as-is they fail
# Pydantic and discard the ENTIRE (otherwise valid) measurement. Coerce string →
# leading float so a malformed OPTIONAL field never costs the measurement.
_COND_NUMERIC = frozenset({"current_density", "electrode_potential_vs_rhe", "temperature_C", "scan_rate"})
_ELECTROLYTE_NUMERIC = frozenset({"concentration", "electrolyte_ph"})


def _coerce_floats(d: dict, numeric: frozenset) -> None:
    """Coerce stringy numeric fields to float in place; drop if no number present."""
    for k in numeric:
        v = d.get(k)
        if isinstance(v, str):
            m = re.search(r"[-+]?\d*\.?\d+", v)
            if m:
                d[k] = float(m.group())
            else:
                d.pop(k, None)


def _coerce_condition(item: dict) -> None:
    cond = item.get("condition")
    if not isinstance(cond, dict):
        return
    _coerce_floats(cond, _COND_NUMERIC)
    el = cond.get("electrolyte")
    if isinstance(el, dict):
        _coerce_floats(el, _ELECTROLYTE_NUMERIC)


def _coerce_confidence(item: dict) -> None:
    """Make ``confidence`` a never-fatal optional annotation.

    Salvage a number from a stringy value ("0.9 (high)" → 0.9), and DROP the key
    entirely when it isn't a number or falls outside [0,1]. Two reasons: an
    optional self-assessment must never delete an otherwise-valid measurement (a
    prose "high" would raise in ``cls(**item)`` and sink the whole item), and a
    wrong-scale value (e.g. 95 read as a percent) must not silently corrupt the
    parser×model matrix — better untagged than wrong. Enforced here rather than as
    a hard schema bound, which would reject the whole instance.
    """
    v = item.get("confidence")
    if v is None:
        return
    if isinstance(v, str):
        m = re.search(r"[-+]?\d*\.?\d+", v)
        v = float(m.group()) if m else None
    # bool is an int subclass — not a valid confidence
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= float(v) <= 1.0:
        item["confidence"] = float(v)
    else:
        item.pop("confidence", None)


def _value_digits(value: Any) -> str:
    """Significant digits of a numeric value, for the mis-citation guard."""
    try:
        return re.sub(r"\D", "", "%g" % float(value))
    except (TypeError, ValueError):
        return ""


def _extract_paper_metadata(sha: str) -> tuple[str | None, str | None]:
    """Best-effort DOI and title from the PDF's first page text.

    Returns ``(doi, title)``; either may be ``None`` when not found or the PDF
    is not on disk (offline tests, scanned-only pages).  Cheap, local, no LLM.
    """
    pdf = _pdf_for_sha(sha)
    if pdf is None:
        return None, None
    import fitz  # heavy; only when a PDF is actually present

    try:
        with fitz.open(pdf) as doc:
            text = doc[0].get_text() if doc.page_count else ""
    except Exception:
        return None, None

    doi: str | None = None
    m = re.search(r"(10\.\d{4,}/\S+)", text)
    if m:
        doi = m.group(1).rstrip(".,;:)]\">'")

    _SKIP = {"article", "letter", "review", "communication", "perspective",
             "editorial", "research", "research article", "original article",
             "full paper", "short communication", "original research"}
    title: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() in _SKIP:
            continue
        if stripped.startswith("http"):
            continue
        title = stripped
        break

    return doi, title


def _resolve_spans(
    ev: Any,
    spans: list[Span],
    paper_sha: str,
    parser_name: str,
    value: Any = None,
    paper_doi: str | None = None,
    paper_title: str | None = None,
) -> dict | None:
    """Build a full Evidence dict from the cited GLOBAL span ids, or ``None`` if invalid.

    When the model cites several spans, Evidence pins to the SINGLE span that
    contains the measured ``value``'s digits — that span's granular bbox + verbatim
    text. This keeps the source box tight (one line/cell) instead of the coarse
    UNION of every cited span, which made every value from one region share one
    block-level box. The digit test mirrors the mis-citation guard; values with
    fewer than 2 digits can't be disambiguated, so they fall back to the union (also
    used when no cited span carries the value, or no value is supplied).
    ``paper.sha256`` + ``parser_name`` are injected. Returns ``None`` when ``ev`` has
    no usable ``spans`` (caller routes to ``errors``).
    """
    if not isinstance(ev, dict):
        return None
    ids = ev.get("spans")
    if isinstance(ids, int):
        ids = [ids]
    if not isinstance(ids, list):
        return None
    cited = [spans[i] for i in ids if isinstance(i, int) and 0 <= i < len(spans)]
    if not cited:
        return None
    # Build the Paper sub-dict once (sha256 mandatory; doi/title best-effort).
    paper_dict: dict[str, str] = {"sha256": paper_sha}
    if paper_doi is not None:
        paper_dict["doi"] = paper_doi
    if paper_title is not None:
        paper_dict["title"] = paper_title
    # Pin to the value-bearing span (granular) when the value is unambiguous.
    vd = _value_digits(value)
    if len(vd) >= 2:
        for p, t, b in cited:
            if vd in re.sub(r"\D", "", t):
                return {
                    "paper": paper_dict, "page": p,
                    "bbox_x0": b[0], "bbox_y0": b[1], "bbox_x1": b[2], "bbox_y1": b[3],
                    "source_text": t, "parser_name": parser_name,
                }
    # Fallback: union bbox + concatenated text (multi-span value, <2 digits, or no value).
    bboxes = [b for _p, _t, b in cited]
    return {
        "paper": paper_dict,
        "page": cited[0][0],
        "bbox_x0": min(b[0] for b in bboxes),
        "bbox_y0": min(b[1] for b in bboxes),
        "bbox_x1": max(b[2] for b in bboxes),
        "bbox_y1": max(b[3] for b in bboxes),
        "source_text": " ".join(t for _p, t, _b in cited),  # verbatim, never stripped
        "parser_name": parser_name,
    }


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


def _process_items(
    items: list,
    spans: list[Span],
    paper_sha: str,
    parser_name: str,
    valid: list[BaseModel],
    errors: list[tuple[Exception, dict]],
    paper_doi: str | None = None,
    paper_title: str | None = None,
) -> None:
    """Resolve GLOBAL span citations, validate, and route each item to valid/errors."""
    for item in items:
        if not isinstance(item, dict):
            errors.append((TypeError(f"item is {type(item).__name__}, expected dict"), {"raw": item}))
            continue
        raw = copy.deepcopy(item)
        type_name = item.get("type")

        if type_name in _MEASUREMENT_NAMES:
            evidence = _resolve_spans(item.get("evidence"), spans, paper_sha, parser_name,
                                      value=item.get("value"),
                                      paper_doi=paper_doi, paper_title=paper_title)
            if evidence is None:
                errors.append((
                    ValueError(
                        f"no valid span citation for {type_name}; "
                        f"evidence={item.get('evidence')!r}"
                    ),
                    raw,
                ))
                continue
            # Mis-citation guard: the cited span(s) should contain the value. For a
            # milli-V/A slot the check is unit-aware (normalize.check_milli_value): a
            # correct conversion ("22 µV/h" → 0.022 mV/h) passes, a raw prefixed value
            # (22) is re-derived to canonical, and a value printed in another unit but
            # not converted ("460 V/h" labelled mV/h, a raw range low end) is refused.
            # Other slots keep the digit-substring test. If the value is not in the
            # span, the model likely cited the wrong span → refuse rather than attach a
            # wrong bbox. Lenient: values with fewer than two digits are exempt.
            v = item.get("value")
            vd = _value_digits(v)
            milli = check_milli_value(v, evidence["source_text"], canonical_unit(type_name))
            if milli is not None and milli[0] == "unit":
                errors.append((
                    ValueError(
                        f"span unit mismatch for {type_name}: value {v!r} is printed as "
                        f"{milli[1]!r} in the cited span, not in {canonical_unit(type_name)!r}"
                    ),
                    raw,
                ))
                continue
            found = (vd in re.sub(r"\D", "", evidence["source_text"]) if milli is None
                     else milli[0] == "ok")
            if len(vd) >= 2 and not found:
                errors.append((
                    ValueError(
                        f"likely mis-citation for {type_name}: value {item.get('value')!r} "
                        f"not found in cited span(s)"
                    ),
                    raw,
                ))
                continue
            item["evidence"] = evidence
            if milli is not None and milli[0] == "ok":
                item["value"] = milli[1]

        _coerce_confidence(item)  # never let an optional confidence sink the item
        _coerce_condition(item)  # salvage stringy numeric condition fields
        try:
            inst = _instantiate(item)
        except (ValidationError, KeyError, TypeError) as exc:
            errors.append((exc, raw))
            continue

        # C2: reject a unit_label that disagrees with the slot's canonical unit
        # (by unit signature, so paper-faithful spellings pass; `V` for an mV slot
        # fails). Only Measurement subclasses carry unit_label.
        if type_name in _MEASUREMENT_NAMES:
            canon = canonical_unit(type_name)
            if canon is not None and not units_match(inst.unit_label, canon):
                errors.append((
                    ValueError(
                        f"unit_label {inst.unit_label!r} != canonical {canon!r} for {type_name}"
                    ),
                    raw,
                ))
                continue
            # C3 (T74): magnitude sanity. C2 passes a value emitted in a prefixed unit
            # (e.g. mV) under the canonical label (V) without conversion — the value is
            # then ~1000× too large but dimensionally "correct". Reject values whose
            # magnitude exceeds the slot's plausible ceiling so an unconverted reading
            # can't slip in. (Tracked slots only — see normalize.PLAUSIBLE_MAX.)
            if not magnitude_ok(type_name, getattr(inst, "value", None)):
                errors.append((
                    ValueError(
                        f"value {getattr(inst, 'value', None)!r} magnitude exceeds the "
                        f"plausible ceiling for {type_name} (canonical unit {canon!r}; "
                        f"likely an unconverted prefixed unit)"
                    ),
                    raw,
                ))
                continue
        valid.append(inst)


def _dedup(valid: list[BaseModel]) -> list[BaseModel]:
    """Drop only TRUE duplicates — same type/value/unit AND same source span.

    Keying on ``source_text`` (not just value) keeps two distinct catalysts that
    happen to report the same value (e.g. 236 mV for A and B) as separate rows;
    only a measurement cited from the identical span (e.g. the same item surfaced
    in two per-page batches of the large-paper fallback) collapses.
    """
    seen: set = set()
    out: list[BaseModel] = []
    for inst in valid:
        ev = getattr(inst, "evidence", None)
        key = (
            type(inst).__name__,
            getattr(inst, "value", None),
            getattr(inst, "unit_label", None),
            getattr(ev, "source_text", None),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(inst)
    return out


def _pdf_for_sha(sha: str) -> Path | None:
    """Locate the source PDF for ``sha`` by hashing every ``papers/*.pdf``.

    Mirrors the viewer's ``_pdf_index`` (tools must not import the viewer). Returns
    ``None`` when no PDF matches — callers treat that as "can't tighten" and keep the
    parser-native bbox, so offline tests (fake shas, no PDF on disk) are unaffected.
    """
    papers = Path(__file__).resolve().parents[3] / "papers"
    for pdf in sorted(papers.glob("*.pdf")):
        try:
            if hashlib.sha256(pdf.read_bytes()).hexdigest() == sha:
                return pdf
        except OSError:
            continue
    return None


def _tighten_evidence(valid: list[BaseModel], paper_sha: str) -> None:
    """Relocate each measurement's Evidence bbox to the exact value text on its PDF
    page, in tight PDF points (bottom-left origin) — so the viewer renders one
    uniform coordinate space for every parser. Pure-local (fitz), no LLM cost.

    No-op when the PDF isn't on disk or the page/text can't be matched: the
    parser-native box is kept (``tighten_bbox`` never fabricates a box).
    """
    pdf = _pdf_for_sha(paper_sha)
    if pdf is None:
        return
    import fitz  # heavy; only when a PDF is actually present

    from .geometry import tighten_bbox

    doc = fitz.open(pdf)
    try:
        for inst in valid:
            ev = getattr(inst, "evidence", None)
            if ev is None or not (1 <= ev.page <= doc.page_count):
                continue
            fallback = (ev.bbox_x0, ev.bbox_y0, ev.bbox_x1, ev.bbox_y1)
            new_bbox, _refined = tighten_bbox(
                doc[ev.page - 1], getattr(inst, "value", None), ev.source_text or "", fallback)
            ev.bbox_x0, ev.bbox_y0, ev.bbox_x1, ev.bbox_y1 = new_bbox
    finally:
        doc.close()


@register("extract", {
    "description": "Schema-first extraction: cached parser output -> LLM -> Pydantic instances.",
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
    response_format: Any = None,
    extra_instruction: str | None = None,
) -> tuple[list[BaseModel], list[tuple[Exception, dict]]]:
    """Run extraction over one cached parser output, ONE LLM call per page.

    The ``provider`` and ``cache`` kwargs exist for test injection; ``cost_meter``
    is optional so direct calls can keep budget tracking honest. ``response_format``
    is the T72 strict-output arm: when set (an OpenAI-style ``json_schema`` dict),
    it is forwarded to ``provider.complete`` — only OpenAI-compatible providers
    honour it. Leave None for the production path (plain JSON + Pydantic).

    ``extra_instruction`` (T74 multi-pass arms) appends one extra line to the user
    message — reason-then-format steering, or a re-query naming the measurement
    types a prior pass missed. ``None`` (default) leaves the production user
    message byte-identical, so the production prompt and its cache key don't move.
    """
    # Resolve + budget-check the provider first (before any file work): a config or
    # budget problem should fail fast. Budget invariant (€50 hard cap): a metered
    # call must price its provider correctly — agent._cost_eur silently falls back to
    # the Sonnet table when a provider has no `prices`, which would mis-charge the cap.
    # The registry providers are all priced, so this is defense-in-depth for a future
    # no-price provider. Guard ONLY the resolved-from-config path: an injected provider
    # (tests, experiments passing prices explicitly) is the caller's responsibility.
    if provider is None:
        db = cost_meter.db_path if cost_meter is not None else "palimpsest.db"
        provider = _resolve_extraction_provider(db)
        if cost_meter is not None and getattr(provider, "prices", None) is None:
            raise ValueError(
                f"extraction provider {getattr(provider, 'name', provider)!r} has no "
                "price table; set verified USD/token rates before metered extraction."
            )

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
        avail = ", ".join(_LOADER.names()) or "(none)"
        raise ValueError(f"unknown skill: {skill_name!r}. Available: {avail}") from None
    norm = build_normalization_prompt([_LOADER.skill_dir(skill_name)])
    jsonschema_str = _schema_for_prompt(_JSONSCHEMA_PATH.read_text(encoding="utf-8"))
    system = _build_system_prompt(skill_body, jsonschema_str, norm)

    spans = _load_spans(parser_name, parser_text)
    paper_doi, paper_title = _extract_paper_metadata(paper_sha)
    valid: list[BaseModel] = []
    errors: list[tuple[Exception, dict]] = []
    if not spans:  # no geometry (e.g. Chandra) → nothing citable
        errors.append((
            ValueError(
                f"parser '{parser_name}' produced no citable spans "
                f"(no geometry/bbox data); extraction requires spans"
            ),
            {"paper_sha": paper_sha, "parser_name": parser_name},
        ))
        return valid, errors

    # One call over the full projection (consistent + cheap); fall back to per-page
    # batching only if the projection is too large to fit. Span ids are GLOBAL, so
    # citations resolve against `spans` regardless of how calls are batched.
    full = _render_projection(spans)
    if len(full) // 4 <= _MAX_PROJECTION_TOKENS:
        batches: list[list[int] | None] = [None]
    else:
        by_page: dict[int, list[int]] = {}
        for i, (page, _t, _b) in enumerate(spans):
            by_page.setdefault(page, []).append(i)
        batches = [ids for _p, ids in sorted(by_page.items())]

    extra = {"response_format": response_format} if response_format is not None else {}
    tail = "\n\nReturn the measurements."
    if extra_instruction:
        tail += "\n\n" + extra_instruction
    for batch in batches:
        content = full if batch is None else _render_projection(spans, batch)
        resp = provider.complete(
            system=system,
            messages=[{"role": "user", "content": content + tail}],
            tools=None,
            cache_breakpoints=["system"],
            **extra,
        )
        if cost_meter is not None:
            from palimpsest.agent import _cost_eur  # lazy: import cycle
            cost_meter.record_llm(
                provider.name,
                _cost_eur(resp.usage, getattr(provider, "prices", None)),
                detail="extract",
            )
        try:
            items = _parse_response(resp.text)
        except ValueError as exc:
            errors.append((exc, {"batch": batch}))
            continue
        _process_items(items, spans, paper_sha, parser_name, valid, errors,
                       paper_doi=paper_doi, paper_title=paper_title)

    # Tighten each Evidence box to the exact value text via the PDF text layer, so
    # boxes are value-tight and in ONE coordinate space (PDF points) the viewer can
    # place for every parser. No-op offline / on scanned pages (keeps native box).
    _tighten_evidence(valid, paper_sha)
    return _dedup(valid), errors
