"""`diagnose_run` tool (T70) — turn a run's flat drop list into a pattern.

`extraction_report` (T58) lists each dropped measurement and its reason. That
answers "what dropped", but not the question the running agent actually needs to
act: *is this a systematic prompt/skill bug or random noise?* A human reading the
log can see that 8 of 11 drops are the same `unit V≠mV` error (fix the skill and
re-extract) while 1 mis-citation is noise (accept). T70 moves that read into the
loop: this tool **buckets** the persisted drop reasons, flags a bucket SYSTEMATIC
when one error recurs, and recommends an action per bucket — so the agent decides.

Pure summary over the same `extraction_runs.errors_json` row T58 persists: no LLM,
no GPU, €0, read-only (only the DDL-on-construct ParserCache/CostMeter already do).
It recommends; it never re-extracts or edits anything (CLAUDE.md: no unsupervised
auto-re-extraction, no second agent).
"""

from __future__ import annotations

import json

from . import register

# A bucket needs this many drops to read as a recurring pattern rather than
# chance. The card's split — 8 unit mismatches (systematic) vs 1 mis-citation
# (noise) — is the canonical case; three strikes is the smallest count that
# isn't plausibly coincidence.
_SYSTEMATIC_MIN = 3

# Per-bucket recommended action. The agent picks among re-extract / fix the skill
# / accept as noise; these phrasings name the likely cause so the choice is
# informed, not a guess.
_REEXTRACT_NOISE = "accept as noise, or re-extract the affected page"
_RULES = [
    # (predicate over a drop dict) -> (bucket label, recommendation)
    (lambda s, r: s == "extract" and "!= canonical" in r,
     ("unit mismatch",
      "re-extract after aligning the skill / normalize canonical units "
      "(e.g. V vs mV)")),
    (lambda s, r: s == "extract" and "mis-citation" in r,
     ("mis-citation", _REEXTRACT_NOISE)),
    (lambda s, r: s == "extract" and "no valid span citation" in r,
     ("unresolvable evidence",
      "check the parser's span projection, or re-extract")),
    (lambda s, r: s == "extract" and "expected dict" in r,
     ("malformed item", "re-extract (the LLM emitted a non-object item)")),
    (lambda s, r: s == "extract",  # remaining extract drops: Pydantic / unknown class
     ("schema/validation error",
      "re-extract; if it recurs, verify the skill targets only real schema "
      "classes (check_skill)")),
    (lambda s, r: s == "shacl",
     ("SHACL violation", "schema-vs-data mismatch; inspect the report")),
    (lambda s, r: s == "insert",
     ("insert refusal",
      "a provenance-less item was refused; check evidence resolution")),
]
_FALLBACK = ("other", "unrecognized drop reason; inspect extraction_report")


@register("diagnose_run", {
    "description": (
        "Diagnose WHY measurements dropped in the latest run of one paper under "
        "one parser: buckets the drops by reason and flags a bucket SYSTEMATIC "
        "when the same error recurs (a prompt/skill bug to fix + re-extract) vs "
        "noise (accept). Recommends an action per bucket. Read-only, €0. Call it "
        "after an extract_paper run that dropped measurements, then decide whether "
        "to re-extract, flag a systematic issue to the human, or proceed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "paper": {
                "type": "string",
                "description": "A PDF path or a 64-hex sha256 of the paper.",
            },
            "parser": {
                "type": "string",
                "description": "Parser whose run to diagnose (default 'mineru').",
            },
        },
        "required": ["paper"],
    },
})
def diagnose_run(paper: str, parser: str = "mineru", *, run_log=None) -> str:
    from palimpsest.runs import ExtractionRunLog

    # Reuse T58's resolver (path|64-hex -> sha) so both tools agree; file untouched.
    from .extraction_report import _resolve_sha

    run_log = run_log if run_log is not None else ExtractionRunLog()
    sha = _resolve_sha(paper)

    run = run_log.latest_run(sha, parser)
    if run is None:
        return (
            f"no extraction run recorded for paper {sha[:8]} under parser "
            f"'{parser}' — run the pipeline first"
        )

    found = run["n_extracted"] + run["n_errors"]
    dropped = found - run["n_inserted"]
    if dropped <= 0:
        return (
            f"{parser} · paper {sha[:8]}: no drops — every extracted "
            f"measurement reached the graph"
        )

    if not run["errors_json"]:
        # Counts show drops but no per-item reasons were stored (pre-T58 row);
        # can't bucket what wasn't recorded.
        return (
            f"{parser} · paper {sha[:8]}: {dropped} dropped, but per-item "
            f"reasons were not recorded (run predates T58)"
        )

    return _render(parser, sha, json.loads(run["errors_json"]))


def _bucket(drop: dict) -> tuple[str, str]:
    """Classify one drop into (label, recommendation). First matching rule wins."""
    stage = str(drop.get("stage", ""))
    reason = str(drop.get("reason", ""))
    for predicate, result in _RULES:
        if predicate(stage, reason):
            return result
    return _FALLBACK


def _render(parser: str, sha: str, drops: list[dict]) -> str:
    # Group drops by bucket label, preserving first-seen order so the output is
    # deterministic. recs[label] holds the recommendation for that bucket.
    counts: dict[str, int] = {}
    recs: dict[str, str] = {}
    for d in drops:
        label, rec = _bucket(d)
        counts[label] = counts.get(label, 0) + 1
        recs[label] = rec

    total = len(drops)
    lines = [f"{parser} · paper {sha[:8]}: {total} drops in {len(counts)} bucket(s):"]
    n_systematic = noise_drops = 0
    for label, n in counts.items():
        systematic = n >= _SYSTEMATIC_MIN
        tag = "SYSTEMATIC" if systematic else "noise"
        if systematic:
            n_systematic += 1
        else:
            noise_drops += n
        pct = round(100 * n / total)
        lines.append(f"  • {label} — {n}/{total} ({pct}%) — {tag}: {recs[label]}")

    if n_systematic:
        lines.append(
            f"→ {n_systematic} systematic pattern(s) + {noise_drops} noise drop(s): "
            f"fix the systematic cause(s) and re-extract; accept the noise."
        )
    else:
        lines.append(
            f"→ no systematic pattern (each bucket < {_SYSTEMATIC_MIN} drops): "
            f"likely noise — accept, or re-extract the affected pages."
        )
    return "\n".join(lines)
