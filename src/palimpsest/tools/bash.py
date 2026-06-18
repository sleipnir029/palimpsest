"""`bash` tool — run a shell command, cwd-pinned to the workspace.

The agent's hands for tests, git, file ops, and notebooks. Unlike
write_file/edit_file (which are confined to the workspace *in code*), bash is a
powerful escape hatch: a shell can use absolute paths or ``cd`` to reach anything
the OS lets it, so its filesystem boundary is NOT enforced here — only the cwd
defaults to the workspace, and ``assert_bash_allowed`` blocks the obvious
un-metered-spend invocations. Real fs/ledger integrity for bash relies on the
human + git (the model Claude Code uses), not on this module. Treat bash as
trusted-but-supervised; the code-enforced guarantees live in the structured
tools, the provenance pipeline, and the in-process budget gate.
"""

from __future__ import annotations

import subprocess

from palimpsest.policy import assert_bash_allowed, workspace_root

from . import register


@register("bash", {
    "description": "Run a bash command in the workspace (tests, git, file ops, marimo). Commands that incur un-metered spend are refused.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "number", "description": "Seconds before the command is killed (default 30)."},
        },
        "required": ["command"],
    },
})
def bash(command: str, timeout: float = 30) -> str:
    assert_bash_allowed(command)  # raises PolicyViolation → surfaced to the agent
    root = workspace_root()
    root.mkdir(parents=True, exist_ok=True)  # a fresh sandbox may not exist yet
    try:
        proc = subprocess.run(
            command, shell=True, cwd=str(root),
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"error: command timed out after {timeout}s"
    out = (proc.stdout + proc.stderr).strip()
    return f"{out}\n[exit {proc.returncode}]" if out else f"[exit {proc.returncode}]"
