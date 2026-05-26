# T32 — open_notebook tool with marimo subprocess

## Why
The agent can launch analysis notebooks on request ("open the overpotentials notebook"). The agent generates the notebook .py file and spawns `marimo edit`.

## Input state
- T26 merged. TUI works.

## Output state
- File `src/palimpsest/tools/open_notebook.py` exports:
  - `def open_notebook(name: str, content: str | None = None, template: str = "default") -> str`:
    1. Compute path `notebooks/{name}.py`.
    2. If `content` is provided: write to path. If `template` is provided and content is None: copy from `notebooks/_template_{template}.py` (must exist).
    3. Spawn `subprocess.Popen(["marimo", "edit", str(path), "--headless", "--port", "0"], stdout=PIPE, stderr=STDOUT, text=True)`.
    4. Read stdout until you see a line with `http://localhost:<port>` (marimo prints this on start).
    5. Return that URL.
  - Registered in TOOLS with schema describing name, optional content, optional template.
- File `tests/test_open_notebook.py` mocks `subprocess.Popen` and asserts: the file is written, Popen is called with right args, URL is parsed correctly.

## Verification
```bash
pixi run pytest tests/test_open_notebook.py -v
# Live:
pixi run python -c "
from palimpsest.tools.open_notebook import open_notebook
url = open_notebook('test_nb', content='import marimo as mo\n\napp = mo.App()\n\n@app.cell\ndef __():\n    print(\"hello\")\n')
print('marimo at', url)
"
# Open the URL in a browser; should show the test_nb cells. Ctrl+C to stop.
```

## Will touch
- `src/palimpsest/tools/open_notebook.py` (new)
- `src/palimpsest/tools/__init__.py` (edit: import)
- `tests/test_open_notebook.py` (new)

## Will NOT touch
- agent.py.

## Out of scope
- Notebook templates → T33.
- Auto-executing notebook code (NEVER — design constraint).

## Notes / references
- Marimo CLI: https://docs.marimo.io/cli/
- `--headless` prevents marimo from opening a browser window automatically.
- `--port 0` lets the OS pick a free port; we read it from stdout.
- The subprocess must be tracked so it can be torn down on agent shutdown — store in `app.notebook_processes` list. (Or for MVP, just leak and rely on user Ctrl+C.)
- Do NOT use `marimo run` (which auto-executes). Always `marimo edit` (interactive).
