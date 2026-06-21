"""T72 — extraction-output cache: never pay twice for the same extraction.

The breadth matrix (`llm_matrix.py`) used to score each `extract()` call and keep
only the aggregate CSV row (`tp`, `recall`, …), discarding the actual extracted
measurements. That made per-tuple error analysis impossible without re-paying — and
when Anthropic credits drained, the haiku/sonnet outputs were lost for good.

This module persists the FULL result of every paid extraction, keyed by everything
that determines it: `(paper_sha, parser, label, mode, prompt_hash)`. A cache hit lets
the matrix skip the provider call entirely (idempotent, resumable) and lets the
re-scorer (`rescore.py`) and error analysis run for €0.

One inspectable JSON file per cell under `experiments/results/extractions/`, so the
record is git-trackable and diffable. This is the parse-once cache's sibling for the
extraction step (the `ParserCache` keys parser output by PDF bytes; this keys LLM
output by paper×parser×model×mode×prompt).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent / "results" / "extractions"
_SCHEMA_VERSION = 1


def _stem(paper_sha: str, parser: str, label: str, mode: str, prompt_hash: str) -> str:
    """Filesystem-safe key. Labels/modes/parsers in this roster are already safe."""
    return f"{paper_sha[:8]}__{parser}__{label}__{mode}__{prompt_hash}"


def path(paper_sha: str, parser: str, label: str, mode: str, prompt_hash: str) -> Path:
    return _DIR / f"{_stem(paper_sha, parser, label, mode, prompt_hash)}.json"


def _serialize_items(valid: list[Any]) -> list[dict]:
    """Pydantic measurement instances → JSON dicts, preserving the class name.

    `model_dump` drops the class (the scorer's `type` discriminator), so we add it
    back explicitly. `evidence.source_text` is kept — the coverage check cross-refs it.
    """
    out: list[dict] = []
    for v in valid:
        d = v.model_dump(mode="json")
        d["type"] = type(v).__name__
        out.append(d)
    return out


def _serialize_errors(errors: list[tuple[Exception, dict]]) -> list[dict]:
    out: list[dict] = []
    for exc, raw in errors:
        out.append({"error": f"{type(exc).__name__}: {exc}", "raw": raw})
    return out


def save(
    *,
    paper_sha: str,
    parser: str,
    label: str,
    mode: str,
    prompt_hash: str,
    model_id: str,
    valid: list[Any],
    errors: list[tuple[Exception, dict]],
    in_tokens: int,
    out_tokens: int,
    latency_s: float,
    temperature: Any = "",
) -> Path:
    """Persist one extraction cell. Returns the file path."""
    _DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "paper_sha": paper_sha,
        "parser": parser,
        "label": label,
        "mode": mode,
        "prompt_hash": prompt_hash,
        "model_id": model_id,
        "temperature": temperature,
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
        "latency_s": round(latency_s, 2),
        "items": _serialize_items(valid),
        "errors": _serialize_errors(errors),
    }
    p = path(paper_sha, parser, label, mode, prompt_hash)
    # default=str so a stray non-JSON raw item can never lose the whole record.
    p.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return p


def load(
    paper_sha: str, parser: str, label: str, mode: str, prompt_hash: str,
    *, model_id: str | None = None,
) -> dict | None:
    """Return the cached payload, or None on miss / model_id mismatch.

    A `model_id` mismatch (the env slug for a label changed since the cache was
    written) is treated as a miss so the cell re-runs against the new model.
    """
    p = path(paper_sha, parser, label, mode, prompt_hash)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if model_id is not None and payload.get("model_id") != model_id:
        return None  # the env slug for this label changed → miss, re-run on the new model
    return payload


def preds_from_items(items: list[dict]) -> list[tuple[str, Any]]:
    """(type, value) tuples for the deterministic scorer."""
    return [(it.get("type"), it.get("value")) for it in items]
