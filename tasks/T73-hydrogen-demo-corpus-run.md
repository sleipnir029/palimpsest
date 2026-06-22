# T73 — Scaled hydrogen demo run (20–25 papers, full pipeline, agentic)

**Status:** paused (2026-06-22) · **Group:** use-case demonstration (thesis) · **Priority:** medium · **Depends:** T71, T36–T39

> **Paused (2026-06-22):** blocked on supervisor sign-off + budget for the 20–25
> paper corpus. This is the generalization test for the T72/T74 guards. A
> preliminary hypothesis test (5 papers × 4 parsers, T72/T74) is banked; the
> scaled run resumes once funding is approved.

## Bigger picture (read first)
The supervisor's "Application/Use Case": *show the system working on 20–25 hydrogen
technology papers, run the full pipeline from an agentic point of view*
(`meetings/19-06-2026.md`). This is the demonstrator that ties everything together —
the new hydrogen skill (T71), the run-time-autonomy machinery (T62/T69/T70), the
parser choice from the comparison (T36–T39), and the queries/plots (T40/T41). The
25-paper run was deliberately deferred at T34 until the parser comparison says which
parsers to keep (cost management) — this card un-defers it once those inputs exist.
Budget: the whole project lives under the **€50 hard cap**; parse-once cache is the
main lever.

## Why
A single end-to-end demonstration on a real corpus is the thesis's evidence that the
agent does the job autonomously (parse → extract → validate → graph → query), not just
on one hand-picked paper.

## Current situation
- 5 OER papers parsed (4 parsers: docling/mineru/dots/paddle; chandra dropped — no
  geometry + timeouts), grounded ground truth (T34/T35, done).
- `pipeline.run_paper` works end-to-end; `demo` CLI exists; `extract_corpus` (T59).
- SPARQL query tool (T53) done; canned `queries/*.rq` + `run_queries.py` (T40) and
  marimo plots (T41) are pending.
- No hydrogen corpus assembled yet; no hydrogen skill yet (T71).

## What to build
1. **Assemble 20–25 hydrogen-technology PDFs** in `papers/` (or a manifest); record
   DOIs + page counts in an `experiments/hydrogen_corpus_manifest.csv` (mirror
   `corpus_manifest.csv`).
2. **Parse** through the cache (the chosen parser set from T36–T39; likely the
   downstream-accuracy winner) — cache short-circuits re-parses, no re-spend.
3. **Run the pipeline** per paper (`run_paper` with the T71 skill) → graph with
   provenance + conditions; log spend against the cap.
4. **Ground truth = multi-LLM PDF-read + aggregation (silver standard), NOT hand-labels.**
   The user cannot hand-label. Method: feed each PDF to several strong models (read the
   *PDF directly*, not a parser's output — keeps GT independent of the parser study),
   then aggregate into a consensus reference. Reuse the T35 pattern (multiple drafters +
   independent adversarial reviewer agents; T35 already did exactly this and caught 4
   errors). Keep high-agreement items; flag disagreements. A quick human *glance* (not
   full labeling) on a sample is cheap insurance — T35 marked its GT
   "grounded-but-recommend-human-glance." State plainly in the thesis that GT is
   silver-standard, with the aggregation method as a limitation.
   ⚠️ **Circularity caveat for the LLM study (T72):** GT built by LLMs that are also
   *under test* is circular. Mitigate: build GT from full-PDF reads by a panel (ideally
   including a model NOT in the T72 matrix, or a stronger setting), score only
   high-consensus items, and human-spot-check. The parser study (T36–T39) is unaffected
   (it holds the LLM fixed and varies the parser).
5. **Queries + plots:** the T40 SPARQL library + T41 marimo plots over the resulting
   graph (these are their own cards — this run produces the data they consume).

## Verification
```bash
pixi run python -m palimpsest demo <one hydrogen pdf>     # prints n_inserted > 0
# graph has measurements from N≈20–25 papers; representative queries return non-empty;
# total spend logged and < €50 (check the CostMeter ledger).
```

## Will touch
- `papers/` (+ `experiments/hydrogen_corpus_manifest.csv`)
- the graph store + cost ledger (via the pipeline only — never hand-written)
- panel-aggregated GT files (mirror `experiments/ground_truth_*.md` + `.pdfread.md` anchors)

## Out of scope
- Hand-labeling (the user can't — GT is LLM-panel-aggregated; see item 4).
- The query library (T40) and plots (T41) themselves — separate cards; this just
  produces their input graph.
- Adding new parsers — use the comparison's chosen set.

## Open decisions
- Final parser set (from T39 result). · How many papers get GT (panel aggregation runs
  on whatever subset you choose for accuracy). · GT panel composition (which models;
  include at least one not in the T72 matrix to limit circularity).
