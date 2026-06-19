# T39 — Downstream extraction accuracy by parser

**Status:** planned · **Group:** evaluation (thesis headline metric) · **Priority:** high

## Bigger picture (read first)
This is the metric the thesis leads with (`report/palimpsest-report.md` §1; contribution
#2): hold the LLM **fixed**, vary the **parser**, and measure how accurately the fixed
model recovers the intended measurements from each parser's output. It is *downstream*
accuracy — distinct from transcription fidelity (T36): a parser can transcribe text
perfectly yet lay it out so extraction fails, or vice versa. Reproducibility is the whole
point — log model version, prompt hash, seeds. See `report/supervisor-answers-2026-06-19.md`
§1a for the shared metric + baseline design, and the plan.

> **Updated 2026-06-19** — corrections from verified state: the fixed extractor is now
> **DeepSeek `deepseek-v4-flash`** (default since T50), not Sonnet; the parser set is the
> **4 with geometry** (docling, mineru, dots, paddle) — **Chandra is excluded** (no bbox
> geometry; reproducibly times out, dropped at T34). Varying the *LLM* (not the parser) is
> a separate study: **T72** (LLM breadth matrix). This card fixes the LLM and varies the parser.

## Metric + baseline (shared design)
- **A predicted measurement is correct** when it matches a ground-truth label on:
  (a) the right slot, (b) value within tolerance (10% relative, or ±0.5 for small
  integers), and (c) the right unit. Report **precision / recall / F1** per parser.
- **Ceiling = human ground truth** (T35); everything is scored against it.
- **Baseline / floor** of the shared ablation = `cheapest-LLM + reference-parser +
  no-skill`; this card is the "vary the parser" axis (LLM + skill fixed).
- Reuse the matching/scoring logic already in `experiments/ab_extract.py`.

## Input state
- T22 (extract) + T35 (grounded ground truth, 5 papers) merged. (Both done.)
- Parser outputs cached for the 4 parsers on all GT papers (T34, done).

## Output state
- `experiments/downstream_accuracy.py`:
  - For each GT paper, for each parser in {docling, mineru, dots, paddle}:
    - `extract(paper_sha, parser_name)` → Pydantic instances.
    - Match each GT label by slot; score exact / within-tolerance / miss per the rule above.
  - Aggregate to per-parser precision/recall/F1 (and % exact / % within-tol / % miss).
- `experiments/downstream_accuracy.csv`.

## Verification
```bash
pixi run python experiments/downstream_accuracy.py && test -f experiments/downstream_accuracy.csv
```

## Will touch
- `experiments/downstream_accuracy.py` (new), `experiments/downstream_accuracy.csv` (generated)
- Reuse: `ab_extract.py` scoring; `extract()` (do not modify it)

## Will NOT touch
- `extract.py` (stable), the schema, the agent loop.

## Out of scope
- Per-slot deep dive — keep at the aggregate level (the chapter T42 narrates it).
- Varying the LLM — that's T72.

## Notes / references
- **Cost is now cheap, not ~$6:** DeepSeek extraction is ≈€0.004–0.008/paper, so
  5 papers × 4 parsers ≈ €0.10–0.16. Cache gives ~90% hit (system+schema+skill identical
  across runs; only parser output changes).
- Chandra: report as "excluded — no geometry," never as accuracy 0.
- This number selects the parser set used by the scaled demo (T73).
