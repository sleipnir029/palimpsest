"""T25 — end-to-end pipeline: one PDF → cached parse → extract → validate → graph.

The first complete vertical slice. ``run_paper`` wires the already-built,
individually-tested pieces into a single call:

    parse_with_cache (T16)  →  extract (T22)  →  validate_instance (T23)
                                              →  RDFStore.insert_extraction (T24)

Nothing here re-implements component logic; this module is integration only.
The cache short-circuit (T16) means a paper whose 5 parser outputs are already
cached parses for free — no pod, no spend — so the pipeline is cheap to re-run.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from .cache import ParserCache
from .cost import CostMeter
from .parsers.runner import parse_with_cache
from .store import RDFStore
from .tools.extract import extract
from .validation import validate_instance

log = logging.getLogger(__name__)


def run_paper(
    pdf_path: str | Path,
    parser_name: str = "mineru",
    skill_name: str = "oer-extraction",
    *,
    store: RDFStore | None = None,
    cache: ParserCache | None = None,
    cost_meter: CostMeter | None = None,
    provider=None,
    run_id: str | None = None,
) -> dict:
    """Run one paper end-to-end and return a summary of counts.

    Steps: parse (cache hit → free) → extract → SHACL-validate each instance
    (drop + log invalid) → insert each valid instance with provenance.

    The ``store``/``cache``/``cost_meter``/``provider`` kwargs are injection
    points (mirroring ``extract``'s own kwargs) so callers — chiefly the test —
    can query the store they passed in. Defaults give a self-contained run for
    the ``demo`` CLI. ``run_id`` ties every inserted triple to one extraction
    run (CostMeter ledger concern; not a schema slot).

    Returns ``{paper_sha, n_extracted, n_validated, n_inserted}``.
    """
    pdf_path = Path(pdf_path)
    cache = cache or ParserCache()
    cost_meter = cost_meter or CostMeter("palimpsest.db")  # honors the €50 cap
    store = store if store is not None else RDFStore()
    run_id = run_id or f"run-{uuid.uuid4()}"

    # 1. Parse via the cache. All-5-cached → short-circuit, no pod, no spend.
    mapping = parse_with_cache([pdf_path], cost_meter, cache)
    sha = next(iter(mapping))

    # 2. Extract (one LLM call). `valid` are Pydantic-valid Measurements that
    #    already carry Evidence; extract-level `errors` (bad/mis-cited items) are
    #    logged inside extract() and not re-counted here — the summary is the
    #    monotonic funnel extracted (=valid) → validated → inserted.
    valid, _errors = extract(
        sha, parser_name, skill_name,
        cost_meter=cost_meter, provider=provider, cache=cache,
    )

    # 3. SHACL gate. Belt-and-suspenders over Pydantic (T23); drop + log failures.
    validated = []
    for inst in valid:
        ok, report = validate_instance(inst)
        if ok:
            validated.append(inst)
        else:
            log.warning("SHACL drop %s: %s", type(inst).__name__, report)

    # 4. Insert with provenance. insert_extraction refuses (ValueError) any
    #    instance whose Evidence is None — CLAUDE.md provenance non-negotiable.
    n_inserted = 0
    for inst in validated:
        try:
            store.insert_extraction(inst, run_id=run_id)
            n_inserted += 1
        except ValueError as e:
            log.warning("insert refused: %s", e)

    return {
        "paper_sha": sha,
        "n_extracted": len(valid),
        "n_validated": len(validated),
        "n_inserted": n_inserted,
    }
