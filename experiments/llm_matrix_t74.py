"""T74 — multi-pass & ensemble extraction vs the T72 single-shot baseline.

Forked from `llm_matrix.py` (kept intact so T72 snapshots stay reproducible). Same
gold, same deterministic scorer, same extraction cache — only the EXTRACTION STRATEGY
changes. Arms (encoded in the cache `mode`, so cells never collide):

  raw          (A) baseline single-shot — REUSES the T72 cache (€0 cache hits).
  reason-first (B) `extract(extra_instruction=REASON_FIRST)`.
  union-k3     (C) 3 samples at temp 0.7, unioned + deduped.
  requery      (D) pass 1 + a targeted pass for the missing measurement types.
  parser-union (E) post-hoc union of the raw cells across all 4 parsers (€0).
  judge        (F) LLM-as-judge precision filter over the union-k3 items.

Spend is fenced to DeepSeek + Gemini (user, 2026-06-21). Frontier rows are NOT run
here — their T72 single-shot cache is the comparison baseline (read separately).

Run:  pixi run python experiments/llm_matrix_t74.py            (docling+paddle, all arms)
      pixi run python experiments/llm_matrix_t74.py --dry-run  (no paid calls)
"""

from __future__ import annotations

import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

import extraction_cache
import multipass
from ab_extract import _score, _score_preds
from llm_matrix import (
    _HEADER, _OPENROUTER, _UsageRecorder, _archive, _f1, _ground_truth,
    _PER_PAPER_CEILING_EUR, _prompt_hash, _temperature,
)
from palimpsest.agent import _USD_TO_EUR
from palimpsest.cache import ParserCache
from palimpsest.cost import BudgetExceeded, CostMeter
from palimpsest.providers import DeepSeekProvider, OpenAICompatProvider
from palimpsest.tools.extract import _MEASUREMENT_NAMES, extract

load_dotenv()

_OUT = Path(__file__).resolve().parent / "llm_matrix_t74.csv"
_RESULTS = _OUT.parent / "results"
_SKILL = "oer-extraction"
_PARSERS = ["docling", "paddle"]          # 100% ceiling → isolates model skill
_ALL_PARSERS = ["mineru", "docling", "dots", "paddle"]  # for parser-union (E)
_SINGLE_ARMS = ["raw", "reason-first", "reason-first-16k", "union-k3", "requery"]
_K = 3
_UNION_TEMP = 0.7

# Cheap, spendable tier. (label, model_id, USD/M in·out, kind, env-for-id)
_MODELS = [
    ("deepseek-flash", "deepseek-v4-flash", 0.14, 0.28, "deepseek", None),
    ("gemini-lite", "", 0.25, 1.50, "openrouter", "OR_GEMINI_LITE_MODEL"),
]


def _prices(price_in: float, price_out: float) -> dict:
    return {
        "input_tokens": price_in / 1_000_000, "output_tokens": price_out / 1_000_000,
        "cache_read_input_tokens": price_in / 1_000_000,
        "cache_creation_input_tokens": price_in / 1_000_000,
    }


def _make_provider(kind: str, model_id: str, prices: dict, temp: float,
                   max_tokens: int | None = None):
    """A fresh, usage-recording provider at the requested temperature.

    `max_tokens` (T74 reason-first retest): raise the output cap so the leading
    `reasoning` field can't truncate the items JSON on a small-budget cheap model.
    """
    if kind == "deepseek":
        inner = DeepSeekProvider(max_tokens=max_tokens) if max_tokens else DeepSeekProvider()
        inner.extra_request = {"thinking": {"type": "disabled"}, "temperature": temp}
    else:  # openrouter (OpenAI-compat)
        kw = dict(model=model_id, base_url=_OPENROUTER, api_key_env="OPENROUTER_API_KEY",
                  name=model_id, temperature=temp)
        if max_tokens:
            kw["max_tokens"] = max_tokens
        inner = OpenAICompatProvider(**kw)
    inner.prices = prices
    return _UsageRecorder(inner)


def _run_single_arm(mode, sha, parser, kind, model_id, prices, meter, cache):
    """Run one single arm live; return (valid, errors, in_tok, out_tok, temperature)."""
    recs: list[_UsageRecorder] = []
    mt = 16384 if mode == "reason-first-16k" else None  # raised output cap retest

    def build(temp):
        r = _make_provider(kind, model_id, prices, temp, max_tokens=mt)
        recs.append(r)
        return r

    kw = dict(skill_name=_SKILL, cache=cache, cost_meter=meter)
    if mode == "raw":
        valid, errors = extract(paper_sha=sha, parser_name=parser, provider=build(0.0), **kw)
    elif mode in ("reason-first", "reason-first-16k"):
        valid, errors = extract(paper_sha=sha, parser_name=parser, provider=build(0.0),
                                extra_instruction=multipass.REASON_FIRST, **kw)
    elif mode == "union-k3":
        valid, errors = multipass.extract_union(sha, parser, build, k=_K, temp=_UNION_TEMP, **kw)
    elif mode == "requery":
        valid, errors = multipass.extract_requery(sha, parser, build, _MEASUREMENT_NAMES, **kw)
    else:
        raise ValueError(mode)
    in_tok = sum(r.in_tokens for r in recs)
    out_tok = sum(r.out_tokens for r in recs)
    temp = _temperature(recs[0]._inner) if recs else ""
    return valid, errors, in_tok, out_tok, temp


def _row(sha, parser, label, model_id, mode, valid_or_preds, truth, in_tok, out_tok,
         latency, temp, prompt_hash, n_errors, price_in, price_out, *, preds=False):
    tp, n_preds, recall, precision = (
        _score_preds(valid_or_preds, truth) if preds else _score(valid_or_preds, truth))
    usd = (in_tok * price_in + out_tok * price_out) / 1_000_000
    eur = usd * _USD_TO_EUR
    return {
        "paper_sha8": sha[:8], "parser": parser, "label": label, "model_id": model_id,
        "role": "T74 multi-pass", "mode": mode,
        "n_valid": n_preds, "n_errors": n_errors, "tp": tp, "gt_total": len(truth),
        "recall": f"{recall:.4f}", "precision": f"{precision:.4f}",
        "f1": f"{_f1(recall, precision):.4f}",
        "in_tokens": in_tok, "out_tokens": out_tok,
        "eur_per_paper": f"{eur:.5f}", "eur_per_tp": f"{eur/tp:.5f}" if tp else "",
        "latency_s": f"{latency:.2f}", "temperature": temp, "prompt_hash": prompt_hash,
    }


def main(dry_run: bool = False) -> None:
    gt = _ground_truth(_PARSERS[0])  # papers with gold cached for docling
    prompt_hash = _prompt_hash()
    cache = ParserCache()
    meter = CostMeter()
    cap = meter.cap
    spent_before = meter.total_eur()
    rows: list[dict] = []
    ran: list[str] = []
    skipped: list[str] = []
    stopped = False

    print(f"BUDGET: €{spent_before:.2f}/{cap:.0f} spent → €{cap - spent_before:.2f} headroom.",
          file=sys.stderr)
    print(f"T74 arms {_SINGLE_ARMS}+parser-union+judge on parsers={_PARSERS}; "
          f"{len(gt)} gold paper(s); models={[m[0] for m in _MODELS]}", file=sys.stderr)
    if dry_run:
        print("DRY RUN: no paid calls.", file=sys.stderr)

    for label, model_id_baked, price_in, price_out, kind, id_env in _MODELS:
        if id_env and not os.environ.get(id_env):
            skipped.append(f"{label} (set ${id_env})"); continue
        if kind == "openrouter" and not os.environ.get("OPENROUTER_API_KEY"):
            skipped.append(f"{label} (no $OPENROUTER_API_KEY)"); continue
        if kind == "deepseek" and not os.environ.get("DEEPSEEK_API_KEY"):
            skipped.append(f"{label} (no $DEEPSEEK_API_KEY)"); continue
        model_id = os.environ[id_env] if id_env else model_id_baked
        prices = _prices(price_in, price_out)

        # --- arms A-D, per parser ------------------------------------------------
        for parser in _PARSERS:
            for sha, truth in gt.items():
                for mode in _SINGLE_ARMS:
                    cached = extraction_cache.load(sha, parser, label, mode, prompt_hash,
                                                   model_id=model_id)
                    if cached is not None:
                        preds = extraction_cache.preds_from_items(cached["items"])
                        rows.append(_row(sha, parser, label, model_id, mode, preds, truth,
                                         cached.get("in_tokens", 0), cached.get("out_tokens", 0),
                                         cached.get("latency_s", 0.0), cached.get("temperature", ""),
                                         prompt_hash, len(cached.get("errors", [])),
                                         price_in, price_out, preds=True))
                        ran.append(f"{label}/{parser}/{mode} {sha[:8]} [cache]")
                        continue
                    if dry_run:
                        skipped.append(f"{label}/{parser}/{mode} {sha[:8]} (dry-run)"); continue
                    try:
                        # Project the arm's REAL call count: union makes k calls, requery
                        # up to 2 — gate on that so the per-arm headroom check isn't a lie
                        # (the €50 cap is still enforced per-call regardless).
                        calls = _K if mode == "union-k3" else 2 if mode == "requery" else 1
                        meter.check_or_raise(_PER_PAPER_CEILING_EUR * calls)
                    except BudgetExceeded as e:
                        skipped.append(f"{label} (budget: {e})"); stopped = True; break
                    try:
                        t0 = time.monotonic()
                        valid, errors, in_tok, out_tok, temp = _run_single_arm(
                            mode, sha, parser, kind, model_id, prices, meter, cache)
                        latency = time.monotonic() - t0
                        extraction_cache.save(
                            paper_sha=sha, parser=parser, label=label, mode=mode,
                            prompt_hash=prompt_hash, model_id=model_id, valid=valid,
                            errors=errors, in_tokens=in_tok, out_tokens=out_tok,
                            latency_s=latency, temperature=temp)
                        rows.append(_row(sha, parser, label, model_id, mode, valid, truth,
                                         in_tok, out_tok, latency, temp, prompt_hash,
                                         len(errors), price_in, price_out))
                        ran.append(f"{label}/{parser}/{mode} {sha[:8]}: "
                                   f"r={rows[-1]['recall']} f1={rows[-1]['f1']}")
                    except Exception as e:  # noqa: BLE001 — one bad cell must not kill the matrix
                        skipped.append(f"{label}/{parser}/{mode} {sha[:8]} "
                                       f"({type(e).__name__}: {e})")
                if stopped:
                    break
            if stopped:
                break

        # --- arm F: judge filter over union-k3, per docling/paddle ---------------
        for parser in _PARSERS:
            for sha, truth in gt.items():
                jcached = extraction_cache.load(sha, parser, label, "judge", prompt_hash,
                                                model_id=model_id)
                if jcached is not None:
                    preds = extraction_cache.preds_from_items(jcached["items"])
                    rows.append(_row(sha, parser, label, model_id, "judge", preds, truth,
                                     jcached.get("in_tokens", 0), jcached.get("out_tokens", 0),
                                     jcached.get("latency_s", 0.0), "", prompt_hash, 0,
                                     price_in, price_out, preds=True))
                    ran.append(f"{label}/{parser}/judge {sha[:8]} [cache]"); continue
                union = extraction_cache.load(sha, parser, label, "union-k3", prompt_hash,
                                              model_id=model_id)
                if union is None or dry_run:
                    skipped.append(f"{label}/{parser}/judge {sha[:8]} "
                                   f"({'dry-run' if dry_run else 'no union-k3 to judge'})")
                    continue
                try:
                    meter.check_or_raise(_PER_PAPER_CEILING_EUR)
                    jrec = _make_provider(kind, model_id, prices, 0.0)
                    t0 = time.monotonic()
                    kept, raw_text = multipass.judge_filter(union["items"], jrec)
                    latency = time.monotonic() - t0
                    from palimpsest.agent import _cost_eur
                    meter.record_llm(jrec.name, _cost_eur(
                        {"input_tokens": jrec.in_tokens, "output_tokens": jrec.out_tokens},
                        jrec.prices), detail="t74-judge")
                    extraction_cache.save(
                        paper_sha=sha, parser=parser, label=label, mode="judge",
                        prompt_hash=prompt_hash, model_id=model_id, valid=[], errors=[],
                        in_tokens=jrec.in_tokens, out_tokens=jrec.out_tokens,
                        latency_s=latency, items=kept)
                    preds = extraction_cache.preds_from_items(kept)
                    rows.append(_row(sha, parser, label, model_id, "judge", preds, truth,
                                     jrec.in_tokens, jrec.out_tokens, latency, "", prompt_hash,
                                     0, price_in, price_out, preds=True))
                    ran.append(f"{label}/{parser}/judge {sha[:8]}: kept {len(kept)}/"
                               f"{len(union['items'])} r={rows[-1]['recall']}")
                except BudgetExceeded as e:
                    skipped.append(f"{label} (budget: {e})"); stopped = True; break
                except Exception as e:  # noqa: BLE001
                    skipped.append(f"{label}/{parser}/judge {sha[:8]} ({type(e).__name__}: {e})")
            if stopped:
                break

        # --- arm E: parser-union of raw cells across all 4 parsers (post-hoc, €0) -
        for sha, truth in gt.items():
            merged: list[dict] = []
            have = []
            for p in _ALL_PARSERS:
                c = extraction_cache.load(sha, p, label, "raw", prompt_hash, model_id=model_id)
                if c is not None:
                    merged.extend(c["items"]); have.append(p)
            if len(have) < 2:
                skipped.append(f"{label}/parser-union {sha[:8]} (only {have} cached)"); continue
            preds = extraction_cache.preds_from_items(multipass.dedup_by_value(merged))
            rows.append(_row(sha, "union", label, model_id, "parser-union", preds, truth,
                             0, 0, 0.0, "", prompt_hash, 0, price_in, price_out, preds=True))
            ran.append(f"{label}/parser-union {sha[:8]} ({'+'.join(have)}): "
                       f"r={rows[-1]['recall']}")
        if stopped:
            break

    # --- arm G: model-union (cheap ∪ cheap, single-shot raw) — post-hoc, €0 -------
    # Two cheap models miss DIFFERENT values (decorrelated errors), so unioning their
    # single-shot outputs recovers model_gaps neither closes alone. Built from the raw
    # cells both models already wrote — no new calls. Labelled across both models.
    model_ids = {m[0]: (os.environ[m[5]] if m[5] else m[1]) for m in _MODELS}
    for parser in _PARSERS:
        for sha, truth in gt.items():
            merged: list[dict] = []
            for mlabel, mid in model_ids.items():
                c = extraction_cache.load(sha, parser, mlabel, "raw", prompt_hash, model_id=mid)
                if c is not None:
                    merged.extend(c["items"])
            if not merged:
                skipped.append(f"model-union/{parser} {sha[:8]} (no raw cells)"); continue
            preds = extraction_cache.preds_from_items(multipass.dedup_by_value(merged))
            rows.append(_row(sha, parser, "model-union", "+".join(model_ids), "model-union",
                             preds, truth, 0, 0, 0.0, "", prompt_hash, 0, 0.0, 0.0, preds=True))
            ran.append(f"model-union/{parser} {sha[:8]}: r={rows[-1]['recall']}")

    with _OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_HEADER); w.writeheader(); w.writerows(rows)
    spent_after = meter.total_eur()
    if rows:
        # Reuse the T72 archiver, tagging the snapshot "t74" instead of a parser name.
        archived = _archive(rows, "t74", spent_before, spent_after, prompt_hash)
        print(f"archived → {archived}")
    print(f"\nwrote {len(rows)} row(s) to {_OUT}")
    for line in ran:
        print("  ran ", line)
    for line in skipped:
        print("  skip", line)
    print(f"\nSPEND: +€{spent_after - spent_before:.4f} → €{spent_after:.2f}/{cap:.0f} "
          f"({cap - spent_after:.2f} left).")
    if stopped:
        print("STOPPED EARLY: budget cap reached.")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv[1:])
