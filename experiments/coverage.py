"""T72 — coverage decomposition: separate the recall CEILING from the model gap.

`recall` collapses two very different failures: the gold value was never in the
parser's text (no model could find it — a parser-coverage ceiling), vs. the value was
present but the model didn't extract it (a model gap). This script measures the first.

For each (parser, paper, gold tuple) it asks: does the text the LLM was actually shown
contain a number within the scorer's tolerance of the gold value? It reuses
`extract._load_spans` so the text is byte-for-byte what extraction saw (not raw parser
JSON) — the faithful upper bound on what any model could possibly cite.

METHOD: exact value-string presence, boundary-anchored. For each gold value we look for
its literal printed form (e.g. "45.16", "3343.37", "240") in the span text, with digit
lookarounds so "45.16" does not match inside "145.167" and "30" does not match inside
"300". This mirrors the extractor's own mis-citation guard (a value is only citable if it
literally appears in a span) — so it is the faithful upper bound on what any model could
extract. Verified against `bd9811a5`: its 4 figure Tafel slopes are present in docling +
paddle but absent from mineru + dots, matching a direct grep of the parse caches.

CAVEAT (documented, not hidden): exact-string presence is NECESSARY, not sufficient. For
distinctive values (236, 52.6, 3343.37, 0.0237, 45.16) it is a strong ceiling. For small
integers (6, 9, 30, 40) a standalone match elsewhere is still possible (e.g. a "30" in
"30 °C" vs a 30 h stability gold), so coverage is OPTIMISTIC there. The per-tuple table
flags which values are distinctive so the analysis can weight them.

Run:  pixi run python experiments/coverage.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ab_extract import GOLD
from palimpsest.cache import ParserCache
from palimpsest.tools.extract import _load_spans

PARSERS = ["mineru", "docling", "dots", "paddle"]
_OUT = Path(__file__).resolve().parent / "results" / "coverage.json"


def _value_strings(value: float) -> set[str]:
    """The literal printed forms of a value to search for ("%g" + bare int)."""
    out = {"%g" % value}
    if value == int(value):
        out.add(str(int(value)))
    return out


def _present(value: float, text: str) -> bool:
    """Does the value literally appear, not embedded in a longer number?

    Digit lookarounds: `45.16` must not match inside `145.167`, `30` not inside `300`.
    `text` has commas pre-stripped so `3,343.37` matches the gold `3343.37`.
    """
    for s in _value_strings(value):
        if re.search(r"(?<!\d)" + re.escape(s) + r"(?!\d)", text):
            return True
    return False


def _distinctive(value: float) -> bool:
    """A value unlikely to appear by coincidence: non-integer, or |v| >= 100."""
    return (value != round(value)) or abs(value) >= 100


def parse_text(cache: ParserCache, sha: str, parser: str) -> str | None:
    """The concatenated span text the LLM saw, or None if this parse isn't cached."""
    p = cache.get_output(sha, parser)
    if p is None:
        return None
    spans = _load_spans(parser, p.read_text(encoding="utf-8"))
    return " ".join(t for _pg, t, _b in spans)


def build() -> dict:
    """Coverage matrix: {parser: {sha: {covered, total, ceiling, tuples:[...]}}}."""
    cache = ParserCache()
    out: dict = {}
    for parser in PARSERS:
        out[parser] = {}
        for sha, tuples in GOLD.items():
            text = parse_text(cache, sha, parser)
            if text is None:
                out[parser][sha] = {"cached": False}
                continue
            # Strip thousands separators so gold "3343.37" matches "3,343.37". Caveat: this
            # also fuses a comma-list like "236,240" → "236240" (a conservative false-
            # NEGATIVE — it can only lower the ceiling, never inflate it).
            text = text.replace(",", "")
            rows = []
            for t_name, val in tuples:
                rows.append({
                    "type": t_name, "value": val,
                    "present": _present(val, text),
                    "distinctive": _distinctive(val),
                })
            covered = sum(r["present"] for r in rows)
            # Distinctive-only ceiling: drops the coincidental-match inflation on small ints.
            dist = [r for r in rows if r["distinctive"]]
            dist_cov = sum(r["present"] for r in dist)
            out[parser][sha] = {
                "cached": True,
                "covered": covered, "total": len(rows),
                "ceiling": round(covered / len(rows), 4) if rows else 0.0,
                "distinctive_covered": dist_cov, "distinctive_total": len(dist),
                "tuples": rows,
            }
    return out


def _print_summary(matrix: dict) -> None:
    shas = sorted({sha for p in matrix.values() for sha in p})
    print("\nCOVERAGE CEILING — fraction of gold tuples whose value appears in the parse")
    print("(distinctive-only in parens; small-int coverage is optimistic — see header)\n")
    hdr = "parser    " + "".join(f"{s[:8]:>14}" for s in shas) + f"{'ALL':>12}"
    print(hdr)
    for parser, papers in matrix.items():
        cells = []
        tot_cov = tot = 0
        for s in shas:
            e = papers.get(s, {})
            if not e.get("cached"):
                cells.append(f"{'—':>14}")
                continue
            tot_cov += e["covered"]; tot += e["total"]
            cells.append(f"{e['covered']}/{e['total']}({e['distinctive_covered']}/{e['distinctive_total']})".rjust(14))
        allcell = f"{tot_cov}/{tot}={tot_cov/tot:.0%}" if tot else "—"
        print(f"{parser:10}" + "".join(cells) + f"{allcell:>12}")
    print()


def main() -> None:
    matrix = build()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    _print_summary(matrix)
    print(f"wrote {_OUT}")


if __name__ == "__main__":
    main()
