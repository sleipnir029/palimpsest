"""`bash` tool — run a shell command, cwd-pinned to the workspace and OS-sandboxed.

The agent's hands for tests, git, file ops, and notebooks. Unlike
write_file/edit_file (confined in code), a shell can use absolute paths or ``cd``
to reach anything the OS user can — so we wrap every command in an OS sandbox
(``sandbox.py``: macOS Seatbelt / Linux bwrap) that **confines file writes/deletes
to the workspace** (reads and network stay open). The pipeline-managed paths
(``store/``, ``cache/``, the ``*.db`` ledger, secrets) are denied to bash too,
matching write_file. Fail-closed: if no sandbox mechanism is available bash
refuses, unless the human opts out with ``/config set bash_sandbox off`` (then it
is the raw, unfenced escape hatch again — the human's responsibility).

bash is still NOT a spend gate: ``assert_bash_allowed`` is a best-effort foot-gun
guard, and the €-budget is enforced in-process on the agent/extract path, not here.
"""

from __future__ import annotations

import os
import signal
import subprocess

from palimpsest import config, sandbox
from palimpsest.policy import PolicyViolation, assert_bash_allowed, workspace_root

from . import register


@register("bash", {
    "description": (
        "Run a bash command in the workspace (tests, git, file ops, marimo). File "
        "WRITES are sandbox-confined to the workspace (reads/network are open); "
        "writes outside it, and to store/cache/*.db/secrets, are refused. Commands "
        "that incur un-metered spend are refused."
    ),
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

    # Default: run under the OS sandbox (writes confined to the workspace). The human
    # can drop the fence with `/config set bash_sandbox off` for the raw escape hatch.
    if config.get_setting("bash_sandbox", "on") != "off":
        if sandbox.mechanism() is None:  # fail-closed: no fence available → refuse
            raise PolicyViolation(
                "bash sandbox required but no OS mechanism is available on this "
                "platform — run `/config set bash_sandbox off` to allow unsandboxed "
                "bash (unsafe: it can write anywhere the OS user can reach)."
            )
        popen_kwargs: dict = {"args": sandbox.wrap(command, root)}
    else:
        popen_kwargs = {"args": command, "shell": True}

    # start_new_session so the whole sandbox-exec→bash→children tree is one process
    # group we can SIGKILL on timeout — otherwise a timed-out command can orphan
    # grandchildren that outlive the kill.
    proc = subprocess.Popen(
        **popen_kwargs, cwd=str(root),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # pid == group leader (new session)
        except ProcessLookupError:
            pass
        proc.communicate()
        return f"error: command timed out after {timeout}s"
    out = (out or "").strip()
    return f"{out}\n[exit {proc.returncode}]" if out else f"[exit {proc.returncode}]"
