# T48 — 5-parser hardware smoke on real GPU

## Why
The deferred T16/T17 verification. The runner and images are mock-tested but the pipeline has
**never run on real GPU hardware**; every downstream metric (T36–T39) and the demo depend on this
actually working. This is the highest-risk unproven step in the whole project.

## Input state
- 5 Docker images built and pushed (T17): docling, mineru, chandra, dots, paddle.
- `RUNPOD_API_KEY`, `RUNPOD_TEMPLATE_<PARSER>`, `RUNPOD_GPU`, `RUNPOD_CLOUD` configured in `.env`.
- ≥1 suitable GPU available (see `runpod-gpu-selection` memory: cu128 floor; cheap ≤24 GB ok for
  docling/mineru; check Ada+ constraints; Vast.ai fallback if scarce).
- 1–2 sample PDFs in `papers/`.

## Output state
- `parse_with_cache` runs all 5 parsers on 1–2 papers against a live pod; outputs land in
  `cache/<sha>/` and `parser_runs` rows are written with **real** `gpu_seconds` / `gpu_cost_eur`.
- `notes/parser-hardware-verify.md` records, per parser: success/failure, wall time, € cost, and
  any CLI / output-path corrections needed. Any correction is also logged in `DEVIATIONS.md`.

## Verification
```bash
pixi run python -m palimpsest parse papers/<sample>.pdf   # or the runner entrypoint in use
ls cache/<sha>/   # docling.json, mineru.json, chandra.md, dots.json, paddle.json all present
sqlite3 palimpsest.db "SELECT parser_name, gpu_cost_eur FROM parser_runs WHERE paper_sha256='<sha>';"
# expect 5 rows with non-zero gpu_cost_eur
```
The verification MUST exit 0 and show 5 cached outputs + 5 ledger rows.

## Will touch
- `notes/parser-hardware-verify.md` (new)
- `DEVIATIONS.md` (if corrections found)
- `cache/`, `palimpsest.db` (data, not code)

## Will NOT touch
- `src/` — unless a real bug is found on hardware; then fix the bug and log it in DEVIATIONS.md.
- `CLAUDE.md`, schema, other task cards.

## Out of scope
- Full 25-paper corpus → T34 (this is a 1–2 paper smoke only).
- Parser accuracy metrics → T36–T39.

## Notes / references
- Budget: ~€0.4–0.9 for 2 papers × 5 parsers. **Check `CostMeter` before the run** (CLAUDE.md:
  every paid call checked first).
- Most likely breakages: SSH keying / pod public-IP assignment, paddle/dots weight loading, parser
  CLI flags, output-path drift vs `parsers/commands.py`. Verify the SCP round-trip first.
- Idle watchdog (`gpu_provider.py`) kills the pod after the hard idle timeout — don't leave it up.
