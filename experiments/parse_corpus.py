"""Parse the local corpus through all 5 parsers + cache it (scaled-down T34).

Drives the existing T16 parse_with_cache over every PDF in papers/. Already-cached
(sha, parser) cells short-circuit (no pod), so re-running only fills missing cells.
Real GPU spend — RunPodSession checks the €50 cap before each pod and bills the
ledger at teardown.

Run:  pixi run python experiments/parse_corpus.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Repo root on path so the root-level `schema` namespace package resolves when this
# script is run directly (pixi run python experiments/parse_corpus.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from palimpsest.cache import ParserCache
from palimpsest.cost import CostMeter
from palimpsest.parsers.runner import parse_with_cache

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("parse_corpus")


def _gpu_spend(meter: CostMeter) -> float:
    row = meter.conn.execute(
        "SELECT COALESCE(SUM(amount_eur), 0) FROM cost_ledger WHERE kind='gpu'"
    ).fetchone()
    return float(row[0])


def main() -> None:
    load_dotenv()
    meter = CostMeter("palimpsest.db")
    cache = ParserCache()

    # Lightest PDF first, heaviest last: the heavy VLM parsers (chandra, dots) can
    # OOM-crash the pod on a large PDF, taking SSH down with it. Ordering the
    # heaviest last means a crash loses only that one paper, not the cheaper ones
    # queued behind it in the same pod.
    pdfs = sorted(Path("papers").glob("*.pdf"), key=lambda p: p.stat().st_size)
    log.info("corpus: %d PDFs", len(pdfs))
    log.info("GPU spend before: €%.4f (cap €%.0f)", _gpu_spend(meter), meter.cap)

    result = parse_with_cache(pdfs, meter, cache)

    log.info("GPU spend after: €%.4f", _gpu_spend(meter))
    print("\n=== completeness ===")
    for sha in cache.list_all_papers():
        present = sorted(result.get(sha, {}).keys())
        missing = [p for p in ParserCache.PARSERS if p not in present]
        flag = "OK" if not missing else f"MISSING {missing}"
        print(f"{sha[:12]}  {flag}  ({len(present)}/5)")


if __name__ == "__main__":
    main()
