"""T27: slash command dispatcher.

Slash commands are explicit control commands, intercepted in the TUI BEFORE the
agent loop — they never reach the LLM and cost nothing. Dead simple: string
match on the first token, no regex. Each handler's one-line ``__doc__`` is what
``/help`` lists, so the registry stays a plain ``dict[str, callable]``.

Scope (T27): only ``/help`` and ``/quit``. ``/budget``, ``/cost``, ``/model``
land in T28; viewer/notebook commands are deferred until needed.
"""

from __future__ import annotations

from collections.abc import Callable


def _help(app, args: list[str]) -> str:
    """list available commands"""
    lines = ["available commands:"]
    for name, fn in SLASH_COMMANDS.items():
        lines.append(f"  /{name} — {(fn.__doc__ or '').strip()}")
    return "\n".join(lines)


def _quit(app, args: list[str]) -> str:
    """exit palimpsest"""
    app.exit()
    return "bye"


SLASH_COMMANDS: dict[str, Callable] = {
    "help": _help,
    "quit": _quit,
}


def dispatch(app, line: str) -> str:
    """Parse a ``/command [args]`` line, run its handler, return the log string.

    Unknown commands return a friendly hint rather than raising, so a typo in
    the TUI never crashes the app.
    """
    parts = line.lstrip("/").split()
    cmd = parts[0] if parts else ""
    handler = SLASH_COMMANDS.get(cmd)
    if handler is None:
        return f"unknown command: /{cmd}. type /help for available commands."
    return handler(app, parts[1:])
