# reports/

Standalone, self-contained HTML reports built from `experiments/` data.

## T72 — parser-conditional extraction accuracy

`t72_report.html` is a single, dependency-free page (data inlined, charts are
hand-built inline SVG — no charting library, no server). Open it by double-click,
or serve the folder for the webfonts to load:

```
python -m http.server -d reports 8000   # then visit /t72_report.html
```

Regenerate it from the authoritative 06-21 snapshots:

```
pixi run python reports/build_t72_report.py
```

- `build_t72_report.py` — reads `experiments/results/llm_matrix_*_2026-06-21.csv`,
  `coverage.json`, `rescore.json`, the `*.meta.json` sidecars and
  `experiments/corpus_manifest.csv`; aggregates per model×parser; emits the HTML.
- `_t72_template.py` — the HTML/CSS/JS template (tokens filled by the builder).

Every figure traces to a cached extraction; struck numbers in the page are real
revisions from the gold audit / re-score, kept visible on purpose.
