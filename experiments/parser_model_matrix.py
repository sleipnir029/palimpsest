"""Phase B — generate a parser×model extraction comparison matrix into a fresh store/.

For each (paper × parser × model) leg, re-extract from the ALREADY-CACHED parse
output and insert every measurement tagged with its extraction model + confidence.
This deliberately calls ``extract`` directly (which reads only the requested
parser's cached output via ParserCache) rather than ``pipeline.run_paper`` —
``run_paper`` → ``parse_with_cache`` runs the full 5-parser set and would spin a
GPU pod for any parser not fully cached (chandra is cached for only 1/5 papers).
We replicate run_paper's validate → insert → run_log tail, minus the parse step.

Real LLM spend. Gated twice: the €75 CostMeter cap (check_or_raise per leg) AND a
self-imposed €10 BATCH ceiling on this run. The viewer MUST be down (single-writer
store). Run from the repo root:  pixi run python experiments/parser_model_matrix.py
Add  --smoke  to do a single leg (~€0.01) as an end-to-end sanity check first.

T72 experiments/ carve-out (like llm_matrix.py): a thesis artifact, not the agent loop.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root → schema/ namespace pkg

# OpenRouter-Gemini leg: set IN-PROCESS only (never .env) so the production
# extraction default (extraction_model=openrouter) is not silently repointed.
# Verified pricing — google/gemini-3.1-flash-lite, $0.25 in / $1.50 out.
os.environ["OPENROUTER_MODEL"] = "google/gemini-3.1-flash-lite"
os.environ["OPENROUTER_PRICE_IN"] = "0.25"
os.environ["OPENROUTER_PRICE_OUT"] = "1.50"

from palimpsest import config
config.load_dotenv()  # DEEPSEEK / GEMINI / OPENROUTER keys from .env

from palimpsest.cost import BudgetExceeded, CostMeter
from palimpsest.cache import ParserCache
from palimpsest.providers import build_provider
from palimpsest.runs import ExtractionRunLog
from palimpsest.store import RDFStore
from palimpsest.tools.extract import extract
from palimpsest.tools.read_paper import read_paper
from palimpsest.validation import validate_instance

PARSERS = ["docling", "mineru", "dots", "paddle"]  # chandra excluded (only 1/5 cached)
# (provider short-name, label stored as palim:extractionModel)
MODELS = [
    ("deepseek", "deepseek-v4-flash"),
    ("deepseek-pro", "deepseek-v4-pro"),
    ("gemini", "gemini-3.5-flash (direct)"),
    ("openrouter", "gemini-3.1-flash-lite (openrouter)"),
]
SKILL = "oer-extraction"
BATCH_CEILING_EUR = 10.0
PER_LEG_RESERVE_EUR = 0.25  # conservative headroom checked against the €75 cap


def _one_leg(sha, parser, provider, label, store, cache, cost, run_log) -> str:
    """Replicate run_paper's extract→validate→insert→record tail for one leg.

    Returns a short status string. extract() reads cache/<sha>/<parser>.* only —
    no parse_with_cache, no pod, no GPU spend.
    """
    run_id = f"matrix-{uuid.uuid4()}"
    valid, errs = extract(sha, parser, SKILL, cost_meter=cost, provider=provider, cache=cache)
    drops = [{"stage": "extract", "reason": str(e)} for e, _ in errs]
    validated = []
    for inst in valid:
        ok, report = validate_instance(inst)
        (validated.append(inst) if ok
         else drops.append({"stage": "shacl", "reason": report, "type": type(inst).__name__}))
    n_inserted = 0
    for inst in validated:
        try:
            store.insert_extraction(inst, run_id=run_id, extraction_model=label)
            n_inserted += 1
        except ValueError as e:
            drops.append({"stage": "insert", "reason": str(e)})
    run_log.record(
        paper_sha256=sha, run_id=run_id, parser_name=parser, skill_name=SKILL,
        n_errors=len(errs), n_extracted=len(valid), n_validated=len(validated),
        n_inserted=n_inserted, errors_json=json.dumps(drops), model=label,
    )
    return f"extracted={len(valid)} validated={len(validated)} inserted={n_inserted}"


def main() -> None:
    smoke = "--smoke" in sys.argv
    papers = sorted(Path("papers").glob("*.pdf"))
    parsers, models = PARSERS, MODELS
    if smoke:
        papers, parsers, models = papers[:1], PARSERS[:1], MODELS[:1]
        print("SMOKE: 1 paper × 1 parser × 1 model")

    cache = ParserCache()
    cost = CostMeter("palimpsest.db")
    run_log = ExtractionRunLog()
    store = RDFStore("store")
    providers = {key: build_provider(key) for key, _ in models}  # openrouter reads env set above

    start = cost.total_eur()
    print(f"start spend €{start:.2f} / cap €{cost.cap:.0f}; batch ceiling €{BATCH_CEILING_EUR:.0f}")
    legs = 0
    for pdf in papers:
        sha = read_paper(str(pdf))["sha256"]  # local hash, free, no LLM
        for parser in parsers:
            if cache.get_output(sha, parser) is None:
                print(f"skip {pdf.name[:20]:20} {parser:8} (no cached parse)")
                continue
            for key, label in models:
                batch = cost.total_eur() - start
                if batch >= BATCH_CEILING_EUR:
                    print(f"\nSTOP: €{BATCH_CEILING_EUR:.0f} batch ceiling reached (batch=€{batch:.2f})")
                    _summary(cost, start, legs); return
                try:
                    cost.check_or_raise(projected_eur=PER_LEG_RESERVE_EUR)  # €75 cap
                except BudgetExceeded as e:
                    print(f"\nSTOP: {e}")
                    _summary(cost, start, legs); return
                try:
                    status = _one_leg(sha, parser, providers[key], label, store, cache, cost, run_log)
                except Exception as e:  # one bad leg must not sink the batch
                    status = f"ERROR {type(e).__name__}: {str(e)[:120]}"
                legs += 1
                print(f"{pdf.name[:20]:20} {parser:8} {label:34} {status}  €{cost.total_eur()-start:.2f}")
    _summary(cost, start, legs)


def _summary(cost: CostMeter, start: float, legs: int) -> None:
    print(f"\n=== {legs} legs · batch spend €{cost.total_eur()-start:.2f} · "
          f"total €{cost.total_eur():.2f}/{cost.cap:.0f} ===")


if __name__ == "__main__":
    main()
