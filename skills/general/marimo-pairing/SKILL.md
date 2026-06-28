---
name: marimo-pairing
description: Pair with the human on a marimo notebook like a coding agent — create, edit, and re-open notebooks the human drives in the browser. Use whenever you build or change a marimo notebook, in any domain.
when_to_use: you are creating, editing, or re-opening a marimo notebook for the human
version: 1.0.0
kind: task
uses:
  - open_notebook
  - write_file
  - sparql_query
---

# Marimo pairing

You and the human pair on the notebook: you write the cells, they run them in the
browser. You never execute notebook code yourself.

## Create / edit / open — always via `open_notebook`
- **Create or replace:** `open_notebook(name="<slug>", content="<full .py>")`.
  The tool writes it to `<workspace>/notebooks/<name>.py` (workspace-confined,
  like `write_file`) and returns the running editor URL. Give the human that URL.
- **Edit an existing notebook:** call `open_notebook` again with the same `name`
  and the **new full `content`** — it overwrites the file and re-opens. Passing
  `content` always wins; omitting it re-opens the current file unchanged (never
  clobbered with a template).
- **Scaffold only:** omit `content` and pass `template=...` to start from an
  engine template — `default` or `parser_comparison` are the only two. Once you
  have real content, pass `content`. Do **not** `read_file` a template — you
  don't need its text.

## Path rules (avoid the workspace fence)
- Let `open_notebook` own the path. Do **not** `write_file`/`read_file` the
  notebook with a bare relative path like `notebooks/x.py` — that resolves to the
  repo root, **outside** the workspace, and is refused (`PolicyViolation`).
- If you must touch the file directly, use the exact path `open_notebook`
  returned — don't retype a relative `notebooks/...` path (the `bash` tool's cwd
  is the workspace, other tools' is the repo root, so a relative guess misfires).

## Driving model — the human runs it
- `open_notebook` always uses `marimo edit` (interactive), never `marimo run`.
  Cells do not execute until the human runs them. State the run order if it
  matters (e.g. "run cell 0 → 1 → 2 first; the rest depend on cell 2").
- The URL carries an access token — it is the human's to open. Don't try to drive
  the browser or fetch the URL yourself.

## Content discipline
- One question per cell, one figure per question. Preview any query with
  `sparql_query` before baking it into a cell.
- Carry provenance through every row you plot (e.g. paper/parser/page) so a point
  traces back to its source.
- `plotly.graph_objects` over plain Python lists — no pandas/`plotly.express`.
