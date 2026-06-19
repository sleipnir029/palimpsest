"""open_notebook tool (T32): generate a marimo notebook and launch `marimo edit`.

The agent gets a notebook `.py` and spawns marimo headless on an OS-picked free
port (`--port 0`), then reads the bound URL back from stdout and returns it.
Always `marimo edit` (interactive), NEVER `marimo run` — the agent must never
auto-execute notebook code (a project non-negotiable; T33 owns templates).

Resolution of the notebook to open, in order:
1. ``content`` given → write it to ``<workspace>/notebooks/<name>.py``.
2. else if ``<workspace>/notebooks/<name>.py`` already exists → open it as-is
   (so "build a notebook with write_file/bash, then open it" works, and a
   re-open never clobbers the agent's own work with a template).
3. else copy the engine template ``notebooks/_template_<template>.py``.

Notebook *instances* live in the workspace (the same place ``write_file`` can put
them — see policy.py), so the tool and the agent agree on where a notebook is.
Templates are read-only engine assets at the repo-root ``notebooks/``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from ..policy import assert_writable, workspace_root
from . import register

# Spawned marimo processes are tracked here but NOT yet reaped (teardown is
# deferred — MVP relies on user Ctrl+C). Module level (not on the agent) so this
# tool needs nothing from agent.py / the TUI; a future shutdown hook can drain it.
_PROCESSES: list[subprocess.Popen] = []

# marimo may announce localhost or the loopback IP depending on host config.
_URL_RE = re.compile(r"http://(?:localhost|127\.0\.0\.1):\d+\S*")


@register("open_notebook", {
    "description": (
        "Generate a marimo notebook and open it in an interactive editor. "
        "Returns the localhost URL of the running marimo session."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Notebook name (lives at <workspace>/notebooks/<name>.py)."},
            "content": {"type": "string", "description": "Notebook .py source. If omitted, an existing notebook of this name is opened, else the template is copied."},
            "template": {"type": "string", "description": "Template name under notebooks/_template_<template>.py (only used when no content and no existing notebook)."},
        },
        "required": ["name"],
    },
})
def open_notebook(name: str, content: str | None = None, template: str = "default") -> str:
    notebooks = workspace_root() / "notebooks"
    notebooks.mkdir(parents=True, exist_ok=True)
    # `name` is agent-controlled — confine the instance to the workspace through the
    # same fence as write_file (resolves `..`/symlinks, raises PolicyViolation on
    # escape), not a raw join that `../../x` would slip through.
    path = assert_writable(str(notebooks / f"{name}.py"))

    if content is not None:
        path.write_text(content, encoding="utf-8")
    elif path.exists():
        pass  # open the agent's existing notebook as-is — never clobber with a template
    else:
        tpl = Path("notebooks") / f"_template_{template}.py"  # engine asset, repo-root
        if not tpl.exists():
            raise FileNotFoundError(f"notebook template not found: {tpl}")
        shutil.copyfile(tpl, path)

    proc = subprocess.Popen(
        ["marimo", "edit", str(path), "--headless", "--port", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _PROCESSES.append(proc)

    for line in proc.stdout:
        match = _URL_RE.search(line)
        if match:
            return match.group(0)

    # stdout closed before marimo announced a URL — it died on startup.
    raise RuntimeError(f"marimo exited before printing a URL (rc={proc.poll()})")
