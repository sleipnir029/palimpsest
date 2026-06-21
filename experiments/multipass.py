"""T74 — multi-pass & ensemble extraction, built on the T72 single-shot core.

T72 proved WHERE recall is lost: ~50% of misses are `model_gap` (the value is in
the parser text, the model just didn't take it). This module tests whether cheap
multi-pass recovers those misses, reusing `extract()` unchanged via one additive
seam (`extra_instruction`). Each arm attacks one miss quadrant:

  reason-first  (B) — `extract(extra_instruction=REASON_FIRST)`: the model emits a
                      `reasoning` field BEFORE `items`, so it enumerates every value
                      on the page before committing to JSON (CRANE/dottxt: reasoning
                      before the constrained part). Attacks FORMAT-induced misses.
  union-k       (C) — sample k times at temp>0, UNION the items (not majority-vote —
                      that suppresses rare-but-correct values), dedup. Attacks
                      STOCHASTIC misses. Recovers nothing systematic.
  re-query      (D) — pass 1, then a 2nd pass naming the measurement types pass 1
                      didn't surface ("extract or state absent"). Attacks SYSTEMATIC
                      misses. NOTE: not benchmarked in the literature — measuring it
                      is the T74 contribution, not a borrowed result.
  parser-union  (E) — union the best per-paper arm across docling ∪ paddle. Attacks
                      the COVERAGE gap (value only in a figure one parser missed).
  judge         (F) — LLM-as-judge precision pass over a union arm: drop values the
                      cited span doesn't support. DROPS, never adds — a precision
                      tool run AFTER recall is bought.

Provenance is preserved: every item still flows through `extract()`'s
`_resolve_spans`, so each carries (paper_sha, parser, page, bbox, source_text).
Union/dedup only ever drop or keep whole provenanced items.

Pure helpers (dedup_by_value / missing_measurement_types / judge_keep /
reachable_recall) are unit-tested in tests/test_multipass.py; the live wrappers are
verified by the T74 run.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from palimpsest.tools.extract import _dedup, extract

# ---------------------------------------------------------------------------
# Instruction strings (the only thing that distinguishes B/D from single-shot)
# ---------------------------------------------------------------------------

# Arm B: reason-then-format. `_parse_response` does json.loads(text) then reads
# body["items"] — it IGNORES extra outer keys, so a leading "reasoning" string
# parses cleanly and is discarded. No schema change, no fence (pure JSON object).
REASON_FIRST = (
    'Before the "items" array, FIRST write a "reasoning" field: in it, enumerate '
    "EVERY numeric measurement stated on this page and which Measurement class each "
    "maps to (overpotential, Tafel slope, mass activity, stability, etc.). Then fill "
    '"items" so that no measurement you listed is omitted. Output exactly one JSON '
    'object: {"reasoning": "<your enumeration>", "items": [ ... ]}.'
)


def requery_instruction(missing_types: list[str]) -> str:
    """Arm D pass-2: name the classes pass-1 didn't surface; ask for them or 'absent'."""
    names = ", ".join(missing_types)
    return (
        "A first extraction pass already ran on this page. It did NOT report any of "
        f"these measurement types: {names}. OER papers commonly report them. Re-read "
        "the spans carefully and extract ONLY measurements of those missing types that "
        "a span actually states (cite the span id). If none are stated on this page, "
        'return {"items": []}. Do not re-report measurements of other types.'
    )


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------

def dedup_by_value(items: list[dict]) -> list[dict]:
    """Collapse the SAME physical measurement across parsers/arms: same (type, value).

    Unlike `extract._dedup` (which also keys on source_text to keep two catalysts
    that report the same number separate WITHIN a parse), the cross-parser/cross-arm
    union must merge docling's "236 mV" with paddle's "236 mV" — same value, different
    cite. First occurrence wins, keeping its provenance.
    """
    seen: set = set()
    out: list[dict] = []
    for it in items:
        key = (it.get("type"), it.get("value"))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def missing_measurement_types(items: list[dict], all_types) -> list[str]:
    """Measurement classes in `all_types` that no item in `items` reported (sorted)."""
    found = {it.get("type") for it in items}
    return sorted(t for t in all_types if t not in found)


def judge_keep(text: str, n_items: int) -> set[int]:
    """Indices the judge marks supported. FAILS OPEN: keep all on any doubt.

    The judge is a precision pass run after we've paid for recall — a malformed or
    wrong-length verdict must never silently delete real extractions, so anything we
    can't trust → keep everything.
    """
    keep_all = set(range(n_items))
    try:
        body = json.loads(_json_blob(text))
        verdicts = body["supported"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return keep_all
    if not isinstance(verdicts, list) or len(verdicts) != n_items:
        return keep_all
    return {i for i, v in enumerate(verdicts) if v}


def reachable_recall(hit: int, gt_total: int, coverage_gap: int) -> float:
    """Recall normalized by the parser coverage ceiling: hit / (reachable gold).

    `coverage_gap` gold tuples are absent from this parser's text (no model could
    cite them), so the reachable denominator is `gt_total - coverage_gap`. Isolates
    model skill from parser limits — the thesis axis. 0.0 when nothing is reachable.
    """
    reachable = gt_total - coverage_gap
    return hit / reachable if reachable > 0 else 0.0


_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _json_blob(text: str) -> str:
    """The JSON object in a model reply — raw, or unwrapped from a ```json fence."""
    t = text.strip()
    if t.startswith("{"):
        return t
    m = _FENCED.search(text)
    return m.group(1) if m else t


# ---------------------------------------------------------------------------
# Live wrappers (integration; verified by the T74 run)
# ---------------------------------------------------------------------------

def extract_union(
    sha: str, parser: str, build_provider: Callable[[float], Any], *,
    k: int = 3, temp: float = 0.7, **kw,
) -> tuple[list[Any], list[tuple[Exception, dict]]]:
    """Arm C: k samples at temp>0, UNION the valid items, dedup. Errors concatenated.

    `build_provider(temp)` returns a fresh provider configured for that temperature
    (so the caller controls DeepSeek-vs-Gemini wiring + usage recording per sample).
    """
    all_valid: list[Any] = []
    all_errors: list[tuple[Exception, dict]] = []
    for _ in range(k):
        valid, errors = extract(
            paper_sha=sha, parser_name=parser, provider=build_provider(temp), **kw)
        all_valid.extend(valid)
        all_errors.extend(errors)
    return _dedup(all_valid), all_errors


def extract_requery(
    sha: str, parser: str, build_provider: Callable[[float], Any], all_types,
    *, temp: float = 0.0, **kw,
) -> tuple[list[Any], list[tuple[Exception, dict]]]:
    """Arm D: pass 1 (single-shot), then one targeted pass for the missing types."""
    valid1, err1 = extract(
        paper_sha=sha, parser_name=parser, provider=build_provider(temp), **kw)
    missing = missing_measurement_types(
        [{"type": type(v).__name__} for v in valid1], all_types)
    if not missing:
        return valid1, err1
    valid2, err2 = extract(
        paper_sha=sha, parser_name=parser, provider=build_provider(temp),
        extra_instruction=requery_instruction(missing), **kw)
    return _dedup(valid1 + valid2), err1 + err2


def judge_filter(
    items: list[dict], provider: Any, *, batch_label: str = "",
) -> tuple[list[dict], str]:
    """Arm F: ask the judge which items their cited span actually supports; drop the rest.

    ONE call for the whole cell (cheap). Returns (kept_items, raw_judge_text) so the
    caller can persist the verdict. Fails open (keeps all) on a bad reply.
    """
    if not items:
        return items, ""
    lines = []
    for i, it in enumerate(items):
        src = (it.get("evidence") or {}).get("source_text", "")
        lines.append(f"[{i}] type={it.get('type')} value={it.get('value')} "
                     f"cited_span={src!r}")
    system = (
        "You verify extracted scientific measurements against the source span they "
        "cite. For each item, decide if the cited span TEXT actually states that "
        "value for that measurement type. Be strict: a value not present in the cited "
        "text, or clearly a different quantity, is NOT supported."
    )
    user = (
        "Items:\n" + "\n".join(lines) +
        f'\n\nReturn exactly: {{"supported": [<{len(items)} booleans, one per item in '
        'order>]}. JSON only.'
    )
    resp = provider.complete(system=system, messages=[{"role": "user", "content": user}],
                             tools=None)
    keep = judge_keep(resp.text, len(items))
    return [it for i, it in enumerate(items) if i in keep], resp.text
