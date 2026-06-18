"""`workspace_status` tool (T57) — the orientation view: "what's here, what have
I done?".

The session-opener for the agentic layer. Composes three already-built
surfaces into one deterministic summary — no LLM, no GPU, €0, and no graph /
ledger / data writes (constructing the run log runs a ``CREATE TABLE IF NOT
EXISTS`` on first use, the same DDL-on-construct as ParserCache / CostMeter; it
writes no rows):

  * ParserCache (T15/T34) — papers present + which parsers have run
  * RDFStore.sparql (T24) — how many measurements reached the graph, per paper
  * ExtractionRunLog (T57) — the last run's counts, for a REAL dropped teaser

The dropped count is the run's recorded ``n_errors + n_extracted - n_inserted``
(candidates that never reached the graph). It is a *teaser*: the count, not the
reasons. The per-item reasons (which value, which guard) are T58's
``extraction_report``, pointed to in the footer. When a paper has measurements
but no recorded run (e.g. a pre-T57 demo insert), the count is reported honestly
and the drop teaser says so rather than inventing a number.

Loose PDFs sitting in the papers dir that the cache has never seen are surfaced
as "needs parsing" (hashed via T07 read_paper so the identity is the real cache
key), so a freshly-dropped-in paper shows up before any pipeline run.
"""

from __future__ import annotations

from pathlib import Path

from . import register

_GRAPH_COUNTS = """
PREFIX palimpsest: <https://w3id.org/palimpsest/>
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?sha (COUNT(?m) AS ?n) WHERE {
  ?m prov:hadPrimarySource ?e .
  ?e palimpsest:paper ?paper .
  ?paper palimpsest:sha256 ?sha .
} GROUP BY ?sha
"""


@register("workspace_status", {
    "description": (
        "Report what's in the workspace and what's been done: PDFs present, which "
        "parsers have run, how many measurements are in the graph per paper, the "
        "last run's dropped-count, and what's pending. Makes no graph/ledger "
        "writes and costs nothing (€0). Use this to orient at the start of a session."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "papers_dir": {
                "type": "string",
                "description": "Directory of source PDFs (default 'papers').",
            },
        },
    },
})
def workspace_status(papers_dir: str = "papers", *, cache=None, store=None, run_log=None) -> str:
    # Lazy imports: cache/store/runs pull in pyoxigraph + the generated schema;
    # defer that cost out of the tools/__init__ scan (sparql_query convention).
    from palimpsest.cache import ParserCache
    from palimpsest.runs import ExtractionRunLog
    from palimpsest.store import RDFStore

    cache = cache if cache is not None else ParserCache()
    store = store if store is not None else RDFStore("store")
    run_log = run_log if run_log is not None else ExtractionRunLog()

    # --- gather (all read-only) ------------------------------------------
    registered = _registered_papers(cache)          # sha -> {filename, page_count}
    parsers = _parsers_by_paper(cache)               # sha -> [parser_name, ...]
    graph_counts = _graph_counts(store)              # sha -> int
    runs = run_log.latest_per_paper()                # sha -> run row
    loose = _loose_pdfs(papers_dir, set(registered)) # sha -> filename (unregistered)

    if not registered and not loose:
        return "workspace status — no papers (read-only, €0)"

    lines = [
        f"workspace status — {len(registered) + len(loose)} papers (read-only, €0)",
        "",
    ]
    pending_parse = 0
    pending_extract = 0

    # Registered papers, deterministic by filename then sha.
    for sha in sorted(registered, key=lambda s: (registered[s]["filename"], s)):
        meta = registered[sha]
        ran = sorted(parsers.get(sha, []))
        n_graph = graph_counts.get(sha, 0)
        lines.append(f"{meta['filename']}  [{sha[:8]} · {meta['page_count']}p]")
        lines.append(f"  parsed     {len(ran)}/{len(ParserCache.PARSERS)}"
                     + (f"  ({', '.join(ran)})" if ran else ""))
        lines.append(f"  extracted  {n_graph} measurements in graph")

        run = runs.get(sha)
        if run is not None:
            candidates = run["n_extracted"] + run["n_errors"]
            dropped = candidates - run["n_inserted"]
            lines.append(
                f"  last run   {candidates} found · {run['n_inserted']} inserted · "
                f"{dropped} dropped  ({run['parser_name']}/{run['skill_name']})"
            )
        elif n_graph > 0:
            lines.append("  last run   (no run metadata — drop count unavailable, see T58)")

        lines.append(f"  → {_status(ran, n_graph)}")
        lines.append("")
        if not ran:
            pending_parse += 1
        elif n_graph == 0:
            pending_extract += 1

    # Loose PDFs on disk the cache has never seen.
    for sha in sorted(loose, key=lambda s: loose[s]):
        lines.append(f"{loose[sha]}  [{sha[:8]} · on disk]")
        lines.append("  → needs parsing (not in cache)")
        lines.append("")
        pending_parse += 1

    lines.append(f"pending: {pending_extract} need extraction, {pending_parse} need parsing")
    lines.append("drop reasons per item: extraction_report (T58)")
    return "\n".join(lines)


def _status(ran: list[str], n_graph: int) -> str:
    if not ran:
        return "needs parsing"
    if n_graph == 0:
        return "needs extraction"
    return "extracted"


def _registered_papers(cache) -> dict[str, dict]:
    # Read the cache's papers table directly (cache.conn is public; mirrors how
    # the /cost command reads cost_meter.conn). list_all_papers() returns only
    # shas; we also want filename + page_count for the display.
    rows = cache.conn.execute(
        "SELECT sha256, filename, page_count FROM papers"
    ).fetchall()
    return {r[0]: {"filename": r[1], "page_count": r[2]} for r in rows}


def _parsers_by_paper(cache) -> dict[str, list[str]]:
    rows = cache.conn.execute(
        "SELECT paper_sha256, parser_name FROM parser_runs"
    ).fetchall()
    out: dict[str, list[str]] = {}
    for sha, parser in rows:
        out.setdefault(sha, [])
        if parser not in out[sha]:
            out[sha].append(parser)
    return out


def _graph_counts(store) -> dict[str, int]:
    # A locked/absent on-disk store must not crash an orientation read.
    try:
        rows = store.sparql(_GRAPH_COUNTS)
    except Exception:  # noqa: BLE001 — degrade gracefully, status is read-only
        return {}
    return {r["sha"]: int(r["n"]) for r in rows if r.get("sha") is not None}


def _loose_pdfs(papers_dir: str, registered: set[str]) -> dict[str, str]:
    d = Path(papers_dir)
    if not d.is_dir():
        return {}
    from .read_paper import read_paper  # T07 — same hashing path as the cache key

    out: dict[str, str] = {}
    for pdf in sorted(d.glob("*.pdf")):
        try:
            sha = read_paper(str(pdf))["sha256"]
        except Exception:  # noqa: BLE001 — skip unreadable, like viewer._pdf_index
            continue
        if sha not in registered:
            out[sha] = pdf.name
    return out
