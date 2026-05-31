"""parse_with_cache — batch-by-parser runner (T16).

Outer loop: parser. Inner loop: PDFs. One pod per parser; image pull is the dominant
RunPod cost, so one pull amortizes over all PDFs. Cache key is `(sha256, parser_name)`
(T15); a fully-cached pair is filled from cache without spinning a pod.

Failure policy (per the T16 card "Notes"): if a parser fails on a single paper, log
the error and continue with the other papers + the other parsers. The failed cell is
OMITTED from the returned mapping (no parser_runs row written, so a future call will
retry that pair). The mapping's "every sha × every parser" invariant therefore holds
only over successful pairs — callers that need true completeness must re-run.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path

from ..cache import ParserCache
from ..tools.read_paper import read_paper
from .commands import PARSERS
from .gpu_provider import RunPodSession

logger = logging.getLogger(__name__)

# Mirrors gpu_provider.EUR_PER_USD by value; kept local so this module doesn't
# import from elsewhere in the package for an FX constant.
_EUR_PER_USD = 0.92


def parse_with_cache(
    pdf_paths: list[Path],
    cost_meter,
    cache: ParserCache,
) -> dict[str, dict[str, Path]]:
    """Parse PDFs with the 5-parser set; reuse cached outputs; one pod per parser.

    Returns `{sha256: {parser_name: Path}}`. Cells are filled from cache where
    available, else from a fresh pod run. Failures are logged + skipped.
    """

    # T07 read_paper hashes from the same bytes it would parse, so the cache
    # key agrees with the rest of the pipeline by construction.
    metas: dict[str, dict] = {}
    for p in pdf_paths:
        info = read_paper(str(p))
        metas[info["sha256"]] = {
            "pdf": Path(p),
            "page_count": info["page_count"],
        }
    shas = list(metas.keys())

    # Register papers FIRST: parser_runs.paper_sha256 FK requires the row to exist
    # (PRAGMA foreign_keys=ON in ParserCache). add_paper is INSERT OR IGNORE so
    # re-registering an already-known paper is a no-op.
    for sha, meta in metas.items():
        cache.add_paper(sha, meta["pdf"].name, meta["page_count"])

    # Prefill the result mapping from cache; later cells (fresh runs) overwrite nothing.
    result: dict[str, dict[str, Path]] = {sha: {} for sha in shas}
    for sha in shas:
        for parser in PARSERS:
            cached = cache.get_output(sha, parser)
            if cached is not None:
                result[sha][parser] = cached

    # Short-circuit: every sha × every parser already cached → no pod work.
    if all(len(result[sha]) == len(PARSERS) for sha in shas):
        return result

    gpus = [g.strip() for g in
            os.environ.get("RUNPOD_GPU", "NVIDIA GeForce RTX 3090").split(",")]
    cloud = os.environ.get("RUNPOD_CLOUD", "secure")

    for parser_name, spec in PARSERS.items():
        unseen = [(sha, metas[sha]["pdf"]) for sha in shas
                  if parser_name not in result[sha]]
        if not unseen:
            logger.info("parser=%s all cached, skipping pod", parser_name)
            continue

        template_id = os.environ[spec["template_id_env"]]
        # idle_hard=2400 covers the chandra worst case (≈1700s on a 12-page paper,
        # T17 pod-verify); ssh timeout=2400 matches. Larger corpora need more.
        with RunPodSession(
            cost_meter,
            template_id=template_id,
            gpu_type=gpus,
            cloud=cloud,
            idle_soft=60,
            idle_hard=2400,
        ) as pod:
            pod.ssh("mkdir -p /workspace/in /workspace/out")
            for sha, pdf in unseen:
                try:
                    pod.pending_work = True
                    pod.scp_up(pdf, f"/workspace/in/{pdf.name}")
                    cmd = spec["run_cmd"](f"in/{pdf.name}", "out")
                    t0 = time.monotonic()
                    pod.ssh(cmd, timeout=2400)
                    seconds = time.monotonic() - t0

                    pod_out = spec["pod_output"](f"in/{pdf.name}", "out")
                    cache_dir = cache.cache_dir / sha
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    local_path = cache_dir / f"{parser_name}{Path(pod_out).suffix}"
                    pod.scp_down(pod_out, local_path)

                    # Per-paper cost = share of the pod's hourly rate over this parse's
                    # wall seconds. cost_ledger (T05) carries the authoritative pod
                    # total via _flush_bill at teardown; this row is for per-parser
                    # attribution / analytics.
                    cost_eur = (
                        (seconds / 3600) * (pod.usd_per_hour or 0) * _EUR_PER_USD
                    )
                    cache.insert_parser_run(
                        sha256=sha,
                        parser_name=parser_name,
                        parser_ver=spec["version"],
                        output_path=str(local_path.relative_to(cache.cache_dir)),
                        gpu_seconds=seconds,
                        gpu_cost_eur=cost_eur,
                        run_id=str(uuid.uuid4()),
                    )
                    result[sha][parser_name] = local_path
                except Exception as e:
                    # No parser_runs row → cache.has_all_parsers stays False for
                    # (sha, parser) → a future call will retry. Log loudly.
                    logger.error(
                        "parser=%s sha=%s failed: %s",
                        parser_name, sha[:12], e,
                    )
                finally:
                    pod.pending_work = False

    return result
