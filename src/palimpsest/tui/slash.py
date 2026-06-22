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

from ..providers import AnthropicProvider, DeepSeekProvider

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
    for name, fn in SLASH_COMMANDS.items():
        lines.append(f"  /{name} — {(fn.__doc__ or '').strip()}")
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
