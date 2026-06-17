"""open_notebook tool (T32): generate a marimo notebook and launch `marimo edit`.

The agent writes a notebook `.py` (from inline `content`, or by copying a
`notebooks/_template_{template}.py` stub) and spawns marimo headless on an
OS-picked free port (`--port 0`), then reads the bound URL back from stdout and
returns it. Always `marimo edit` (interactive), NEVER `marimo run` — the agent
must never auto-execute notebook code (a project non-negotiable; T33 owns
templates).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

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
            "name": {"type": "string", "description": "Notebook name (written to notebooks/<name>.py)."},
            "content": {"type": "string", "description": "Notebook .py source. If omitted, the template is copied."},
            "template": {"type": "string", "description": "Template name under notebooks/_template_<template>.py."},
        },
        "required": ["name"],
    },
})
def open_notebook(name: str, content: str | None = None, template: str = "default") -> str:
    notebooks = Path("notebooks")
    notebooks.mkdir(parents=True, exist_ok=True)
    path = notebooks / f"{name}.py"

    if content is not None:
        path.write_text(content, encoding="utf-8")
    else:
        tpl = notebooks / f"_template_{template}.py"
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
