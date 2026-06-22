"""T27: slash command dispatcher.

Slash commands are explicit control commands, intercepted in the TUI BEFORE the
agent loop — they never reach the LLM and cost nothing. Dead simple: string
match on the first token, no regex. Each handler's one-line ``__doc__`` is what
``/help`` lists, so the registry stays a plain ``dict[str, callable]``.

Scope (T28): ``/help``, ``/quit`` (T27) plus ``/budget``, ``/cost``, ``/model``;
viewer/notebook commands are deferred until needed.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import NamedTuple

from ..parsers.commands import PARSERS
from ..providers import (
    AnthropicProvider,
    DeepSeekProvider,
    ORCHESTRATION_PROVIDERS,
    PROVIDER_FACTORIES,
)
from .themes import THEMES

# Config keys surfaced by /config, and which provider each one (re)builds.
_CONFIG_KEYS = ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "RUNPOD_API_KEY")
_KEY_PROVIDER = {"DEEPSEEK_API_KEY": "deepseek", "ANTHROPIC_API_KEY": "sonnet"}

# /model X -> provider class for the agent loop. Keys MUST stay in sync with
# providers.ORCHESTRATION_PROVIDERS (the membership gate /use checks). DeepSeek is
# the T50 default; Anthropic is the kept fallback (`sonnet` and `anthropic` are the
# same class). haiku/gemini are named but can't drive the loop — handled explicitly
# so the message is clearer than "unknown model".
_PROVIDERS: dict[str, Callable] = {
    "deepseek": DeepSeekProvider,
    "sonnet": AnthropicProvider,
    "anthropic": AnthropicProvider,
}
_NOT_IMPLEMENTED = {"haiku", "gemini"}


def _help(app, args: list[str]) -> str:
    """list available commands"""
    lines = ["available commands:"]
    for name in VISIBLE_COMMANDS:  # /model is a hidden alias of /use orchestration
        lines.append(f"  /{name} — {(SLASH_COMMANDS[name].__doc__ or '').strip()}")
    return "\n".join(lines)


def _quit(app, args: list[str]) -> str:
    """exit palimpsest"""
    app.exit()
    return "bye"


def _budget(app, args: list[str]) -> str:
    """raise the budget cap, e.g. /budget 75"""
    try:
        n = int(args[0])
    except (IndexError, ValueError):
        return "usage: /budget <int euros>"
    result = app.cost_meter.set_budget(n)  # T05: writes the DB, refuses below spend
    if result.startswith("refused"):
        return result
    spent = app.cost_meter.total_eur()
    return f"budget cap → €{n} (spent €{spent:.2f}, headroom €{n - spent:.2f})"


def _cost(app, args: list[str]) -> str:
    """show spend: total, LLM vs GPU, last 10 ledger entries"""
    # cost.py has no aggregation method and is off-limits (T28 card), so read the
    # ledger directly off its connection — read-only, no cost.py edit.
    conn = app.cost_meter.conn
    lines = [f"total spent: €{app.cost_meter.total_eur():.4f}"]
    by_kind = {
        kind: total
        for kind, total in conn.execute(
            "SELECT kind, COALESCE(SUM(amount_eur), 0) FROM cost_ledger GROUP BY kind"
        )
    }
    lines.append(f"  llm €{by_kind.get('llm', 0):.4f} / gpu €{by_kind.get('gpu', 0):.4f}")
    rows = conn.execute(
        "SELECT ts, kind, provider, amount_eur, detail FROM cost_ledger "
        "ORDER BY rowid DESC LIMIT 10"  # rowid, not ts: ts is 1s-resolution and ties
    ).fetchall()
    if rows:
        lines.append("last entries:")
        for ts, kind, provider, amount, detail in rows:
            lines.append(f"  €{amount:.4f}  {kind}  {provider or '-'}  {detail or ''}")
    return "\n".join(lines)


def _model(app, args: list[str]) -> str:
    """switch LLM provider: /model sonnet|deepseek"""
    x = args[0] if args else ""
    if x in _NOT_IMPLEMENTED:
        return f"provider '{x}' not implemented yet"
    cls = _PROVIDERS.get(x)
    if cls is None:
        return f"unknown model: {x}. options: sonnet, deepseek"
    try:
        provider = cls()
    except Exception as exc:  # noqa: BLE001 — e.g. missing API key; surface, don't crash
        return f"could not switch to {x}: {exc}"
    app.agent.provider = provider
    # Persist so the choice survives restart (shared db with the ledger).
    from .. import config
    config.set_setting("orchestration_model", x, db_path=app.cost_meter.db_path)
    # New model ⇒ the prompt cache built for the old one no longer applies.
    return f"switched to {provider.name} (prompt cache reset)"


def _use(app, args: list[str]) -> str:
    """set a role's model: /use orchestration|extraction|parser <name>"""
    from .. import config
    from ..providers import PROVIDER_FACTORIES

    if len(args) < 2:
        return "usage: /use <orchestration|extraction|parser> <name>"
    role, name = args[0], args[1]
    db = app.cost_meter.db_path
    if role in ("orchestration", "orch"):
        # Orchestration is Anthropic-wire only — gate on the single source of truth
        # before delegating to /model (which constructs + hot-swaps + persists).
        from ..providers import ORCHESTRATION_PROVIDERS

        if name not in ORCHESTRATION_PROVIDERS:
            opts = ", ".join(ORCHESTRATION_PROVIDERS)
            return (f"'{name}' can't drive the agent loop (Anthropic-wire only). "
                    f"options: {opts}. For other models use /use extraction {name}.")
        return _model(app, [name])
    if role in ("extraction", "extract"):
        if name not in PROVIDER_FACTORIES:
            return f"unknown provider: {name}. options: {', '.join(PROVIDER_FACTORIES)}"
        config.set_setting("extraction_model", name, db_path=db)
        return f"extraction → {name} (applies to the next extract_paper)"
    if role == "parser":
        from ..parsers.commands import PARSERS
        if name not in PARSERS:
            return f"unknown parser: {name}. options: {', '.join(PARSERS)}"
        config.set_setting("parser_name", name, db_path=db)
        return f"parser → {name} (default for the next extract_paper)"
    return f"unknown role: {role}. options: orchestration, extraction, parser"


def _resume_trim(msgs: list[dict]) -> list[dict]:
    """Trim a transcript to end at the last *clean* assistant answer.

    The next turn appends a user message, so the restored history must end with a
    completed assistant text turn (valid role alternation, no dangling tool_use). A
    normally-finished run already does; this trims a tail left dangling by a
    cancelled/killed run (its last record can be a tool_result with no reply)."""
    out = list(msgs)
    while out:
        last = out[-1]
        content = last.get("content")
        if last.get("role") == "assistant" and isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "text" for b in content
        ) and not any(
            isinstance(b, dict) and b.get("type") == "tool_use" for b in content
        ):
            return out
        out.pop()
    return out


def _resume_recap(msgs: list[dict], keep: int = 10) -> str:
    """One line per human/agent text exchange (tool blocks omitted), tail-capped."""
    lines: list[str] = []
    for m in msgs:
        role, content = m.get("role"), m.get("content")
        if role == "user" and isinstance(content, str):
            lines.append(f"  ❯ {content.strip()[:76]}")
        elif role == "assistant" and isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
            if text:
                lines.append(f"  · {text[:76]}")
    if len(lines) > keep:
        lines = [f"  (+{len(lines) - keep} earlier)"] + lines[-keep:]
    return "\n".join(lines) if lines else "  (no text exchanges)"


def _resume(app, args: list[str]) -> str:
    """reload the previous session's context into the agent: /resume"""
    msgs = _resume_trim(list(app.agent.session.load()))
    if not msgs:
        return "no prior session to resume."
    app.agent.messages = msgs  # restore context so the next turn continues with it
    return f"resumed {len(msgs)} message(s) from the last session:\n{_resume_recap(msgs)}"


def _theme(app, args: list[str]) -> str:
    """switch UI theme: /theme [scriptorium|vellum|oxide|catalogue]"""
    from .. import config
    from .themes import THEMES

    if not args:
        cur = getattr(app, "theme", None)
        listing = ", ".join(f"{n} (active)" if n == cur else n for n in THEMES)
        return f"themes: {listing}"
    name = args[0]
    if name not in THEMES:
        return f"unknown theme: {name}. options: {', '.join(THEMES)}"
    app.theme = name  # Textual re-renders the whole screen with the new palette
    refresh = getattr(app, "_refresh_topbar", None)
    if refresh:
        refresh()
    config.set_setting("ui_theme", name, db_path=app.cost_meter.db_path)
    return f"theme → {name}"


def _config(app, args: list[str]) -> str:
    """show config keys (masked), or set one: /config set KEY VALUE"""
    from .. import config

    if not args:
        db = getattr(getattr(app, "cost_meter", None), "db_path", "palimpsest.db")
        keys = "\n".join(
            f"  {k}={'set' if os.environ.get(k) else '(unset)'}" for k in _CONFIG_KEYS
        )
        roles = "\n".join(
            f"  {label}={config.get_setting(key, dflt, db_path=db)}"
            for label, key, dflt in (
                ("orchestration", "orchestration_model", "deepseek"),
                ("extraction", "extraction_model", "deepseek"),
                ("parser", "parser_name", "mineru"),
            )
        )
        return f"{keys}\nmodels:\n{roles}"
    if args[0] != "set" or len(args) < 3:
        return "usage: /config | /config set KEY VALUE"
    key, value = args[1], " ".join(args[2:])
    note = config.set_value(key, value)  # writes workspace .env + os.environ
    # If it's the active provider's key, rebuild the provider so it takes effect now.
    name = _KEY_PROVIDER.get(key)
    if name:
        try:
            app.agent.provider = _PROVIDERS[name]()
            note += f" — provider {name} reloaded"
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the TUI
            note += f" (provider reload failed: {exc})"
    return note


def _undo(app, args: list[str]) -> str:
    """revert the workspace to the previous turn (records a revert commit)"""
    from .. import versioning

    r = versioning.undo_last_turn()
    if not r.undone:
        return r.detail
    if not r.changed:  # already at the previous turn — nothing to restore
        return r.detail
    files = ", ".join(r.changed[:8]) + ("…" if len(r.changed) > 8 else "")
    tail = f" [{r.revert_sha[:8]}]" if r.revert_sha else ""
    return f"{r.detail}{tail}: restored {len(r.changed)} file(s): {files}"


SLASH_COMMANDS: dict[str, Callable] = {
    "help": _help,
    "quit": _quit,
    "budget": _budget,
    "cost": _cost,
    "model": _model,
    "use": _use,
    "theme": _theme,
    "resume": _resume,
    "config": _config,
    "undo": _undo,
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


# --- autocomplete (app-phase) ------------------------------------------------
# The TUI menu reads everything it needs from `menu_for`; all command/argument
# knowledge stays here so app.py stays a dumb view. `/model` dispatches but is NOT
# in VISIBLE_COMMANDS — it's a hidden alias of `/use orchestration` (consolidated
# surface). `anthropic` is accepted by the handlers but unlisted (canonical name is
# `sonnet`); de-advertised, not removed, so persisted *_model=anthropic rows survive.
VISIBLE_COMMANDS = (
    "help", "quit", "budget", "cost", "use", "theme", "resume", "config", "undo",
)

_PROVIDER_GLOSS = {
    "deepseek": "cheap default",
    "sonnet": "Anthropic fallback",
    "gemini": "OpenAI-compat (extraction only)",
}
_ROLE_GLOSS = {
    "orchestration": "agent loop driver",
    "extraction": "extraction pass",
    "parser": "PDF parser",
}
_THEME_GLOSS = {
    "scriptorium": "warm ink & parchment",
    "vellum": "aged-paper light",
    "oxide": "cool graphite",
    "catalogue": "slate-navy",
}
_CONFIG_KEY_GLOSS = {
    "DEEPSEEK_API_KEY": "DeepSeek key",
    "ANTHROPIC_API_KEY": "Anthropic key",
    "RUNPOD_API_KEY": "RunPod key (GPU)",
}


class Menu(NamedTuple):
    """What the autocomplete should show for the current input value."""

    usage: str | None              # header line, e.g. "usage: /use <role> <name>"
    rows: list[tuple[str, str]]    # (token, gloss), already filtered by the partial
    prefix: str                    # prepend on completion, e.g. "/use orchestration "
    label_slash: bool              # command mode → display "/help"; arg values → bare


def _provider_rows(names) -> list[tuple[str, str]]:
    # Drop the `anthropic` alias from the advertised list (canonical: sonnet).
    return [(n, _PROVIDER_GLOSS.get(n, "")) for n in names if n != "anthropic"]


def _parser_gloss(name: str) -> str:
    v = PARSERS[name].get("version", "")
    return f"{v} (default)" if name == "mineru" else v


def _arg_options(app, cmd: str, completed: list[str]) -> tuple[str | None, list[tuple[str, str]]]:
    """Options for the positional arg currently being typed (``completed`` = the
    args already finished before it). ``[]`` options + a usage string means a
    free-text arg (show the usage header only); ``(None, [])`` means no help."""
    pos = len(completed)
    if cmd == "budget":
        return ("usage: /budget <int euros>  e.g. 75", []) if pos == 0 else (None, [])
    if cmd == "model":  # hidden alias, still guided once typed
        return ("usage: /model <name>", _provider_rows(ORCHESTRATION_PROVIDERS)) if pos == 0 else (None, [])
    if cmd == "use":
        if pos == 0:
            return ("usage: /use <role> <name>",
                    [(r, _ROLE_GLOSS[r]) for r in ("orchestration", "extraction", "parser")])
        if pos == 1:
            role = completed[0]
            if role in ("orchestration", "orch"):
                return ("usage: /use orchestration <name>", _provider_rows(ORCHESTRATION_PROVIDERS))
            if role in ("extraction", "extract"):
                return ("usage: /use extraction <name>", _provider_rows(PROVIDER_FACTORIES))
            if role == "parser":
                return ("usage: /use parser <name>", [(n, _parser_gloss(n)) for n in PARSERS])
        return (None, [])
    if cmd == "theme":
        if pos == 0:
            cur = getattr(app, "theme", None)
            rows = [
                (n, _THEME_GLOSS.get(n, "") + (" (active)" if n == cur else ""))
                for n in THEMES
            ]
            return ("usage: /theme <name>", rows)
        return (None, [])
    if cmd == "config":
        if pos == 0:
            return ("usage: /config set KEY VALUE", [("set", "set a config key")])
        if pos == 1 and completed[0] == "set":
            return ("usage: /config set KEY VALUE",
                    [(k, _CONFIG_KEY_GLOSS.get(k, "")) for k in _CONFIG_KEYS])
        if pos == 2 and completed[0] == "set":
            return ("usage: /config set KEY VALUE", [])  # free VALUE
        return (None, [])
    return (None, [])


def menu_for(app, value: str) -> Menu | None:
    """Autocomplete state for an input value, or None to close the menu.

    Two modes: command (``/pre`` with no space → match VISIBLE_COMMANDS) and
    argument (``/cmd …`` → live values for the current positional arg)."""
    if not value.startswith("/"):
        return None
    head, sep, rest = value.partition(" ")
    cmd = head[1:]
    if not sep:  # still typing the command name
        matches = [c for c in VISIBLE_COMMANDS if c.startswith(cmd)]
        if not matches:
            return None
        rows = [(c, (SLASH_COMMANDS[c].__doc__ or "").strip()) for c in matches]
        return Menu(usage=None, rows=rows, prefix="/", label_slash=True)
    if cmd not in SLASH_COMMANDS:  # includes the hidden "model"
        return None
    toks = rest.split()
    if rest == "" or rest.endswith(" "):
        completed, partial = toks, ""
    else:
        completed, partial = toks[:-1], toks[-1]
    usage, options = _arg_options(app, cmd, completed)
    if usage is None and not options:
        return None
    filtered = [(t, g) for t, g in options if t.startswith(partial)]
    prefix = head + " " + (" ".join(completed) + " " if completed else "")
    return Menu(usage=usage, rows=filtered, prefix=prefix, label_slash=False)
