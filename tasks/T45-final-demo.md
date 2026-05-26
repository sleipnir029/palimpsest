# T45 — Final demo recording

## Why
The defence needs a demo. 15 minutes, end-to-end.

## Input state
- All previous tasks merged. System works.

## Output state
- File `thesis/demo.mp4` — 15-minute screen recording covering:
  - 0–2 min: project motivation, design choices.
  - 2–6 min: `pixi run tui`. Open TUI. Show chat. Ask "parse paper X and extract overpotentials". Show cache hit on second call.
  - 6–9 min: `pixi run viewer`. Open browser. Show PDF + extracted values. Hover values, show bbox highlight.
  - 9–12 min: SPARQL queries via `/cost`, `/budget`. Show ledger. Show one notebook (`marimo edit notebooks/thesis/01_parser_comparison.py`).
  - 12–15 min: brief summary of parser comparison results from the thesis.
- File `thesis/demo_script.md` — the spoken-word script for the recording.

## Verification
```bash
test -f thesis/demo.mp4 && du -h thesis/demo.mp4
# Recording exists and is < 500MB.
```

## Will touch
- `thesis/demo.mp4` (new, binary; consider whether to commit or just link from README)
- `thesis/demo_script.md` (new)

## Will NOT touch
- Anything else. This is the recording, not new code.

## Out of scope
- Live demos beyond this recording — the recording IS the deliverable.

## Notes / references
- Use OBS or QuickTime. 1080p, 30 fps is fine.
- Rehearse once. Record. Don't over-polish.
- 1 hour total.
