"""Parser-comparison notebook (T33 template, for the week-5 benchmark).

Copied by the `open_notebook` tool for `template="parser_comparison"`. Loads a
CSV of per-parser metric scores and draws one bar subplot per metric. The CSV is
produced by the parser-benchmark task and may not exist yet — this template is
guarded so it opens cleanly beforehand. Marimo notebook; open with `marimo edit`.
"""

import marimo

__generated_with = "0.23.8"
app = marimo.App()


@app.cell
def _():
    import csv
    from pathlib import Path

    import marimo as mo
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    return Path, csv, go, make_subplots, mo


@app.cell
def _(Path, csv):
    # Expected long-form CSV, one row per (parser, metric):
    #   parser,metric,value
    #   docling,precision,0.91
    #   mineru,precision,0.88
    CSV_PATH = Path("experiments/parser_comparison.csv")

    parsers, metrics, values = [], [], []
    if CSV_PATH.exists():
        with CSV_PATH.open() as fh:
            for row in csv.DictReader(fh):
                parsers.append(row["parser"])
                metrics.append(row["metric"])
                values.append(float(row["value"]))
    return CSV_PATH, metrics, parsers, values


@app.cell
def _(CSV_PATH, go, make_subplots, metrics, mo, parsers, values):
    if not parsers:
        out = mo.md(
            f"No parser results yet — expected `{CSV_PATH}` with columns "
            "`parser,metric,value`. Run the parser benchmark to create it."
        )
    else:
        ordered_metrics = sorted(set(metrics))
        ordered_parsers = sorted(set(parsers))
        fig = make_subplots(rows=1, cols=len(ordered_metrics),
                            subplot_titles=ordered_metrics)
        for col, metric in enumerate(ordered_metrics, start=1):
            score = {p: v for p, m, v in zip(parsers, metrics, values) if m == metric}
            fig.add_trace(
                go.Bar(x=ordered_parsers,
                       y=[score.get(p) for p in ordered_parsers],
                       showlegend=False),
                row=1, col=col,
            )
        fig.update_layout(title="Parser comparison by metric")
        out = fig
    out
    return


@app.cell
def _(mo):
    mo.md(
        """
        ## How to modify
        - **CSV location/shape:** edit `CSV_PATH`; expected long form
          `parser,metric,value` (one row per parser × metric).
        - **Layout:** one column per metric with independent y-axes (scales differ —
          precision vs. seconds). Swap `rows`/`cols` in `make_subplots` to stack.
        - **Subset:** narrow `ordered_parsers` / `ordered_metrics` to focus a comparison.
        """
    )
    return


if __name__ == "__main__":
    app.run()
