"""T72 — LLM breadth-matrix extraction benchmark (frontier / cheap / small-open / local).

For each model x each paper-with-ground-truth, run extraction (`tools=None`, the
non-agentic path), score recall/precision/F1 against the hand-built ground truth with
the SAME deterministic logic as `ab_extract.py`, and record €/paper + latency to
`experiments/llm_matrix.csv`. Cost is a REPORTED axis: plot accuracy vs €/paper.

Scoring is deterministic (numeric match within tolerance), NOT DeepEval — see the
T72 card for why (DeepEval's LLM-judge metrics fit free-text/RAG, not numeric
extraction, and grading LLMs with an LLM is mildly circular).

Run:  pixi run python experiments/llm_matrix.py
Live + paid for cloud models. Models whose API key / endpoint is absent are SKIPPED
(logged), so the run never errors out and the CSV is always written. Pricing for
non-Anthropic / non-DeepSeek models is NOT baked — supply verified rates via env
(<PREFIX>_PRICE_IN / _PRICE_OUT, USD per 1M tokens) or the €/paper column is left
blank and only the token counts are recorded.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Repo root + this dir on path: resolve the `palimpsest` package and sibling
# `ab_extract` when run directly (pixi run python experiments/llm_matrix.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from ab_extract import GOLD, _score  # reuse the deterministic scorer + multi-paper gold
from palimpsest.agent import _USD_TO_EUR
from palimpsest.cache import ParserCache
from palimpsest.cost import BudgetExceeded, CostMeter
from palimpsest.providers import (
    AnthropicProvider,
    DeepSeekProvider,
    GeminiProvider,
    OpenAICompatProvider,
)
from palimpsest.skills import SkillLoader
from palimpsest.tools.extract import _JSONSCHEMA_PATH, _MEASUREMENT_NAMES, extract

load_dotenv()

_OUT = Path(__file__).resolve().parent / "llm_matrix.csv"
_PARSER = "mineru"
_SKILL = "oer-extraction"

_HEADER = [
    "paper_sha8", "parser", "label", "model_id", "role", "mode",
    "n_valid", "n_errors", "tp", "gt_total",
    "recall", "precision", "f1",
    "in_tokens", "out_tokens", "eur_per_paper", "eur_per_tp", "latency_s",
    "temperature", "prompt_hash",
]


@dataclass
class Spec:
    label: str
    model_id: str            # baked only for authoritative providers; else read from model_env
    role: str
    factory: Callable        # () -> provider (reads model_env at call time when set)
    price_in: float | None   # USD per 1M input tokens (None = not verified -> blank cost)
    price_out: float | None  # USD per 1M output tokens
    key_env: str | None      # required API-key env var (None = local / no key); skip if unset
    model_env: str | None = None  # if set, the model id is REQUIRED from this env var
                                  # (skip the row when unset) — no guessed ids
    strict_capable: bool = False  # marks rows that get the extra strict run (Part C).
                                  # Set only on OpenRouter rows. Claude/DeepSeek direct use
                                  # the Anthropic wire (no response_format); Gemini direct
                                  # IS OpenAI-compat so it *could* take strict, but is left
                                  # raw-only by config (free tier — not worth the arm).


_OPENROUTER = "https://openrouter.ai/api/v1"


def _openrouter(label, role, model_env, price_in, price_out):
    """A spec routed through OpenRouter (one OPENROUTER_API_KEY for all of them).

    The slug is read from `model_env` in .env (YOU control which model runs). The price
    is the verified rate (openrouter.ai, 2026-06-19) for the RECOMMENDED slug in
    .env.example — if you point the env at a different model, update the price here too,
    or the €/paper column will be wrong. A wrong/unset slug skips-and-logs.
    """
    return Spec(
        label, "", role,
        lambda: OpenAICompatProvider(
            model=os.environ[model_env], base_url=_OPENROUTER,
            api_key_env="OPENROUTER_API_KEY", name=os.environ[model_env]),
        price_in, price_out, "OPENROUTER_API_KEY", model_env=model_env,
        strict_capable=True)


# Roster, by routing — Stage 1 (model selection on mineru; see the T72 plan). A
# PRINCIPLED sample of the model space, not arbitrary (rationale per model in
# .env.example): one representative per major family the direct providers don't cover,
# spanning closed↔open and frontier↔cheap, with within-family scaling pairs
# (OpenAI frontier↔mini, DeepSeek flash↔pro, Gemini flash↔flash-lite, Claude tiers) to
# isolate "does size help within a family?". Slugs verified live on openrouter.ai
# (2026-06-20); prices are the per-model-page rate for the recommended slug — re-confirm
# before trusting €/paper if you swap a slug. Opus 4.8 is a ONE-TIME ceiling here, pruned
# before the Stage-2 parser grid (it's not the production model).
SPECS: list[Spec] = [
    # ---- OpenRouter hub (one key); YOU set the slugs in .env, rationale in .env.example.
    # These are the strict-capable rows (Part C raw-vs-strict). Claude/DeepSeek are NOT
    # here — OpenRouter doubles Claude's price, and DeepSeek runs direct (the agent default).
    # OpenAI = the 3rd major closed frontier lab, + its cheap tier (within-OpenAI scaling):
    _openrouter("openai-frontier", "OpenAI frontier (closed)", "OR_OPENAI_MODEL", 2.50, 15.0),
    _openrouter("openai-mini", "OpenAI small (closed)", "OR_OPENAI_MINI_MODEL", 0.75, 4.50),
    # Qwen = the strongest OPEN-weight family; the cost-value 1M-ctx flagship:
    _openrouter("qwen-plus", "Qwen3.7-Plus (open, value)", "OR_QWEN_MODEL", 0.32, 1.28),
    # Gemini Flash-Lite via OpenRouter = ultra-cheap baseline + the strict-arm Gemini
    # (the free-tier Gemini below is raw-only); pairs with gemini-3.5-flash for scaling:
    _openrouter("gemini-lite", "Gemini Flash-Lite (cheap)", "OR_GEMINI_LITE_MODEL", 0.25, 1.50),
    # ---- Anthropic direct (authoritative pricing; avoids OpenRouter's 2x Claude markup) ----
    Spec("haiku-4.5", "claude-haiku-4-5", "frontier-small probe",
         lambda: AnthropicProvider(model="claude-haiku-4-5", name="claude-haiku-4-5"),
         1.0, 5.0, "ANTHROPIC_API_KEY"),
    Spec("sonnet-4.6", "claude-sonnet-4-6", "mid frontier",
         lambda: AnthropicProvider(model="claude-sonnet-4-6", name="claude-sonnet-4-6"),
         3.0, 15.0, "ANTHROPIC_API_KEY"),
    Spec("opus-4.8", "claude-opus-4-8", "frontier ceiling (one-time, pruned)",
         lambda: AnthropicProvider(model="claude-opus-4-8", name="claude-opus-4-8"),
         5.0, 25.0, "ANTHROPIC_API_KEY"),
    # ---- DeepSeek direct (authoritative; the agent default; already funded) ----
    Spec("deepseek-flash", "deepseek-v4-flash", "production default under test",
         lambda: DeepSeekProvider(), 0.14, 0.28, "DEEPSEEK_API_KEY"),
    Spec("deepseek-pro", "deepseek-v4-pro", "within-provider big",
         lambda: DeepSeekProvider(model="deepseek-v4-pro"), 0.435, 0.87, "DEEPSEEK_API_KEY"),
    # ---- Google Gemini direct, FREE tier (no card; €0 within the free quota) ----
    # Set GEMINI_MODEL=gemini-3.5-flash; raw-only (free tier has no response_format arm).
    Spec("gemini-free", "", "google free tier",
         lambda: GeminiProvider(model=os.environ["GEMINI_MODEL"]),
         0.0, 0.0, "GEMINI_API_KEY", model_env="GEMINI_MODEL"),
    # ---- Local floor: LM Studio (MLX) default :1234, or Ollama :11434 (free; €0) ----
    Spec("local", "", "free/local floor",
         lambda: OpenAICompatProvider(
             model=os.environ["LOCAL_MODEL"],
             base_url=os.environ.get("LOCAL_BASE_URL") or "http://localhost:1234/v1",
             api_key="local", name=os.environ["LOCAL_MODEL"]),
         0.0, 0.0, None, model_env="LOCAL_MODEL"),
]


class _UsageRecorder:
    """Wraps a provider to accumulate token usage across complete() calls.

    Lets the matrix compute €/paper itself from verified rates (rather than via
    extract's cost_meter, which would mis-cost an unknown-price provider through the
    Sonnet default). Forwards `name`/`prices` so extract() is none the wiser.
    """

    def __init__(self, inner):
        self._inner = inner
        self.name = inner.name
        self.prices = getattr(inner, "prices", None)
        self.in_tokens = 0
        self.out_tokens = 0

    def complete(self, *args, **kwargs):
        # Disable prompt caching for a clean per-paper cost: a single extraction call
        # gets no reuse benefit, only a write premium + split token accounting. We also
        # count EVERY input tier below, because DeepSeek/Gemini auto-cache server-side
        # regardless (they report most input under cache_read_*), and ignoring those
        # tiers undercounts cost ~50x (the T72 first-run bug).
        kwargs["cache_breakpoints"] = None
        r = self._inner.complete(*args, **kwargs)
        u = r.usage
        self.in_tokens += (
            u.get("input_tokens", 0)
            + u.get("cache_read_input_tokens", 0)
            + u.get("cache_creation_input_tokens", 0)
        )
        self.out_tokens += u.get("output_tokens", 0)
        return r


def _f1(recall: float, precision: float) -> float:
    return 2 * recall * precision / (recall + precision) if (recall + precision) else 0.0


def _temperature(inner) -> object:
    """The configured sampling temperature, for the reproducibility column.

    OpenAI-compat providers hold it as `.temperature`; DeepSeek fixes it in
    `extra_request` (`{"temperature": 0}`). Anthropic sets neither (API default), so
    the column is left blank for it — honestly absent, not falsely 0.
    """
    t = getattr(inner, "temperature", None)
    if t is None:
        t = getattr(inner, "extra_request", {}).get("temperature", "")
    return t


def _prompt_hash() -> str:
    """Reproducibility anchor: the skill body is the prompt's domain content."""
    body = SkillLoader().load(_SKILL)
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def _strict_response_format() -> dict:
    """Build the Part-C strict json_schema from the generated schema's reusable defs.

    The model is told to emit `evidence: {"spans": [...]}` (the runtime fills bbox/
    page/etc.), so the generated Evidence def (which requires bbox) is NOT reused —
    we substitute a span-only Evidence. Condition/Electrolyte + the 5 enums ARE reused
    verbatim. For OpenAI strict:true every object must be closed (additionalProperties
    false) and list ALL properties in `required`; optionality is expressed by allowing
    null. Condition's enum-typed slots are $ref without a null branch, so we wrap each as
    `anyOf[{$ref}, null]` — otherwise `required` would force an enum value the paper
    rarely states. Providers that don't support this schema error out and are logged
    (skip-and-log) — itself a finding, not a crash.
    """
    src = json.loads(_JSONSCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]
    keep = ["Electrolyte", "Condition", "CellTypeFamilyEnum", "ElectrolyteFamilyEnum",
            "IRCorrectionEnum", "NormalizationBasisEnum", "ScanRateRegimeEnum"]
    defs = {k: src[k] for k in keep}
    cond = defs["Condition"]
    for sub in cond["properties"].values():
        if "$ref" in sub:  # enum ref → make nullable so required-all doesn't force it
            sub["anyOf"] = [{"$ref": sub.pop("$ref")}, {"type": "null"}]
    cond["required"] = list(cond["properties"])
    defs["Electrolyte"]["required"] = list(defs["Electrolyte"]["properties"])
    defs["EvidenceSpans"] = {
        "type": "object", "additionalProperties": False,
        "properties": {"spans": {"type": "array", "items": {"type": "integer"}}},
        "required": ["spans"],
    }
    item = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "type": {"type": "string", "enum": sorted(_MEASUREMENT_NAMES)},
            "value": {"type": "number"},
            "unit_label": {"type": ["string", "null"]},
            "condition": {"anyOf": [{"$ref": "#/$defs/Condition"}, {"type": "null"}]},
            "evidence": {"$ref": "#/$defs/EvidenceSpans"},
        },
        "required": ["type", "value", "unit_label", "condition", "evidence"],
    }
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {"items": {"type": "array", "items": item}},
        "required": ["items"], "$defs": defs,
    }
    return {"type": "json_schema",
            "json_schema": {"name": "measurements", "strict": True, "schema": schema}}


def _ground_truth(parser: str = _PARSER) -> dict[str, list]:
    """{paper_sha: [(type, value), ...]} for every cached paper that has gold.

    Gold lives in `ab_extract.GOLD` (one source of truth, keyed by the PDF's sha256 =
    the `cache/<sha>/` dir name). A paper is scored only if BOTH its `<parser>.json`
    cache and a GOLD entry exist — so pointing `parser` at docling/dots/paddle for the
    Stage-2 sweep reuses the same gold with no other change.
    """
    cached = {p.parent.name for p in Path("cache").glob(f"*/{parser}.json")}
    return {sha: GOLD[sha] for sha in sorted(cached) if sha in GOLD}


# Rough €/paper ceiling for the budget pre-check: ~25K in + 3K out at the priciest
# model in the matrix (Opus 5/25 USD/M) ≈ €0.18; round up so check_or_raise refuses a
# call that would breach the €50 cap BEFORE it's made.
_PER_PAPER_CEILING_EUR = 0.20


def main(dry_run: bool = False, parser: str = _PARSER) -> None:
    gt = _ground_truth(parser)
    prompt_hash = _prompt_hash()
    strict_rf = _strict_response_format()  # built once (also validates the schema assembles)
    cache = ParserCache()
    # Real project ledger. extract() records spend to it; we ALSO call
    # meter.check_or_raise() before each paid run so the €50 hard cap (CLAUDE.md
    # non-negotiable) refuses a call that would breach it — extract() itself only
    # records, it does not gate. The CSV's €/paper is computed separately from the
    # verified rates below.
    meter = CostMeter()
    cap = meter.cap
    spent_before = meter.total_eur()  # ALL prior LLM+GPU spend, every run (not just this one)
    rows: list[dict] = []
    ran: list[str] = []
    skipped: list[str] = []
    stopped = False

    print(f"BUDGET: €{spent_before:.2f} already spent of €{cap:.0f} cap "
          f"(LLM+GPU, all prior runs) → €{cap - spent_before:.2f} headroom; "
          "this benchmark adds to it.", file=sys.stderr)
    if not gt:
        print(f"no cached paper (parser={parser}) with machine-readable gold; "
              "writing header only.", file=sys.stderr)
    else:
        print(f"scoring {len(gt)} GT paper(s) on parser={parser}: "
              + ", ".join(f"{s[:8]}({len(t)})" for s, t in gt.items()), file=sys.stderr)
    if dry_run:
        print("DRY RUN: building providers + writing header only; NO paid calls.",
              file=sys.stderr)

    for spec in SPECS:
        if spec.key_env and not os.environ.get(spec.key_env):
            skipped.append(f"{spec.label} (no ${spec.key_env})")
            continue
        if spec.model_env and not os.environ.get(spec.model_env):
            skipped.append(f"{spec.label} (set ${spec.model_env} to a verified model id)")
            continue
        if dry_run:
            skipped.append(f"{spec.label} (dry-run)")
            continue
        model_id = os.environ[spec.model_env] if spec.model_env else spec.model_id
        # raw mirrors production; strict (Part C) runs only for rows marked
        # strict_capable (the OpenRouter rows) — see the Spec.strict_capable note.
        modes = ["raw"] + (["strict"] if spec.strict_capable else [])
        for sha, truth in gt.items():
            for mode in modes:
                try:
                    meter.check_or_raise(_PER_PAPER_CEILING_EUR)  # €50 gate — refuse before spend
                except BudgetExceeded as e:
                    skipped.append(f"{spec.label} (budget: {e})")
                    stopped = True
                    break
                try:
                    inner = spec.factory()
                    if spec.price_in is not None and spec.price_out is not None:
                        # Accurate per-model ledger cost (else _cost_eur falls back to the
                        # Sonnet table — fine as a ceiling, but set it right when we know it).
                        inner.prices = {
                            "input_tokens": spec.price_in / 1_000_000,
                            "output_tokens": spec.price_out / 1_000_000,
                            "cache_read_input_tokens": spec.price_in / 1_000_000,
                            "cache_creation_input_tokens": spec.price_in / 1_000_000,
                        }
                    provider = _UsageRecorder(inner)
                    t0 = time.monotonic()
                    valid, errors = extract(
                        paper_sha=sha, parser_name=parser, skill_name=_SKILL,
                        provider=provider, cache=cache, cost_meter=meter,
                        response_format=strict_rf if mode == "strict" else None,
                    )
                    latency = time.monotonic() - t0
                except Exception as e:  # noqa: BLE001 — one bad model/mode must not kill the matrix
                    skipped.append(
                        f"{spec.label}/{mode} on {sha[:8]} (error: {type(e).__name__}: {e})")
                    continue
                tp, n_preds, recall, precision = _score(valid, truth)
                f1 = _f1(recall, precision)
                if spec.price_in is not None and spec.price_out is not None:
                    usd = (provider.in_tokens * spec.price_in
                           + provider.out_tokens * spec.price_out) / 1_000_000
                    eur_val = usd * _USD_TO_EUR
                    eur = f"{eur_val:.5f}"
                    eur_tp = f"{eur_val / tp:.5f}" if tp else ""  # cost per CORRECT extraction
                else:
                    eur = ""  # rate not verified — record tokens, leave cost blank
                    eur_tp = ""
                rows.append({
                    "paper_sha8": sha[:8], "parser": parser, "label": spec.label,
                    "model_id": model_id, "role": spec.role, "mode": mode,
                    "n_valid": n_preds, "n_errors": len(errors),
                    "tp": tp, "gt_total": len(truth),
                    "recall": f"{recall:.4f}", "precision": f"{precision:.4f}", "f1": f"{f1:.4f}",
                    "in_tokens": provider.in_tokens, "out_tokens": provider.out_tokens,
                    "eur_per_paper": eur, "eur_per_tp": eur_tp, "latency_s": f"{latency:.2f}",
                    "temperature": _temperature(provider._inner),
                    "prompt_hash": prompt_hash,
                })
                ran.append(f"{spec.label}/{mode} on {sha[:8]}: "
                           f"recall={recall:.0%} f1={f1:.2f} €={eur or 'n/a'}")
            if stopped:
                break
        if stopped:
            break

    with _OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_HEADER)
        w.writeheader()
        w.writerows(rows)

    spent_after = meter.total_eur()
    print(f"\nwrote {len(rows)} row(s) to {_OUT}")
    for line in ran:
        print("  ran ", line)
    for line in skipped:
        print("  skip", line)
    print(f"\nSPEND: this run +€{spent_after - spent_before:.4f} → "
          f"€{spent_after:.2f} of €{cap:.0f} total ({cap - spent_after:.2f} left).")
    if stopped:
        print("STOPPED EARLY: budget cap reached. Raise it with the CostMeter or /budget.")


if __name__ == "__main__":
    args = sys.argv[1:]
    # Stage 2 (parser sweep) is just `--parser=docling|dots|paddle`; default mineru.
    parser = next((a.split("=", 1)[1] for a in args if a.startswith("--parser=")), _PARSER)
    main(dry_run="--dry-run" in args, parser=parser)
