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

# Config keys surfaced by /config. LLM keys + RunPod creds: the API key AND the
# per-parser template ids (RunPod spins pods up FROM a template — the key alone can't
# parse). OpenRouter is deliberately absent: CLAUDE.md bars LLM gateways from the
# runtime (experiment-only carve-out), so it stays out of the agent's /config.
_RUNPOD_TEMPLATE_KEYS = tuple(dict.fromkeys(p["template_id_env"] for p in PARSERS.values()))
_CONFIG_KEYS = (
    "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "OPENROUTER_API_KEY", "OPENROUTER_MODEL",  # extraction gateway (CLAUDE.md carve-out)
    "RUNPOD_API_KEY", *_RUNPOD_TEMPLATE_KEYS,
)
# Which orchestration provider a key (re)builds when set live. Only the Anthropic-wire
# loop drivers; GEMINI/RunPod keys are saved but don't hot-swap the agent provider.
_KEY_PROVIDER = {"DEEPSEEK_API_KEY": "deepseek", "ANTHROPIC_API_KEY": "sonnet"}

# /model X -> provider class for the agent loop. Keys MUST stay in sync with
# providers.ORCHESTRATION_PROVIDERS (the membership gate /use checks). DeepSeek is
# the T50 default; Anthropic is the kept fallback (`sonnet` and `anthropic` are the
# same class). haiku/gemini are named but can't drive the loop — handled explicitly
# so the message is clearer than "unknown model".
_PROVIDERS: dict[str, Callable] = {
    "deepseek": DeepSeekProvider,
    "deepseek-pro": PROVIDER_FACTORIES["deepseek-pro"],
    "sonnet": AnthropicProvider,
    "haiku": PROVIDER_FACTORIES["haiku"],
    "anthropic": AnthropicProvider,
}
_NOT_IMPLEMENTED = {"gemini"}  # extraction-only (OpenAI-compat, no tool use)

# Two-level model selection for /use (T-app): provider → its models. Each model is
# (id, comment, factory); factory is the priced PROVIDER_FACTORIES name for the
# Anthropic-wire models, or None for gateway providers that carry the chosen model in
# an env var. Per the user's choice the menu shows names + comments, no prices.
_PROVIDER_MODELS: dict[str, dict] = {
    "deepseek": {"loop": True, "desc": "DeepSeek (Anthropic-wire)", "models": [
        ("deepseek-v4-flash", "cheap default", "deepseek"),
        ("deepseek-v4-pro", "bigger, pricier", "deepseek-pro"),
    ]},
    "anthropic": {"loop": True, "desc": "Anthropic (fallback)", "models": [
        ("claude-sonnet-4-6", "mid frontier", "sonnet"),
        ("claude-haiku-4-5", "small / cheap", "haiku"),
    ]},
    "gemini": {"loop": False, "desc": "Google (extraction only)", "env": "GEMINI_MODEL",
               "models": [
        ("gemini-flash-latest", "newest Flash (drifting alias)", None),
        ("gemini-2.5-flash", "Gemini 2.5 Flash", None),
        ("gemini-3.5-flash", "Gemini 3.5 Flash", None),
    ]},
    "openrouter": {"loop": False, "desc": "OpenRouter gateway (extraction only)",
                   "env": "OPENROUTER_MODEL", "free": True, "models": [
        ("openai/gpt-4o-mini", "cheap OpenAI", None),
        ("openai/gpt-4o", "OpenAI frontier", None),
        ("anthropic/claude-3.5-sonnet", "Claude via gateway", None),
        ("google/gemini-2.5-flash", "Gemini via gateway", None),
        ("deepseek/deepseek-chat", "DeepSeek via gateway", None),
        ("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B", None),
        ("z-ai/glm-4.6", "Zhipu z.ai GLM 4.6", None),
    ]},
}


def _providers_for_role(role: str) -> list[str]:
    """Providers offered for a role: all four for extraction, loop-capable for orch."""
    extract = role in ("extraction", "extract")
    return [p for p, s in _PROVIDER_MODELS.items() if extract or s["loop"]]


def _provider_model_rows(provider: str) -> list[tuple[str, str]]:
    return [(m, c) for m, c, _f in _PROVIDER_MODELS[provider]["models"]]


def _factory_for(provider: str, model: str | None) -> str:
    """The PROVIDER_FACTORIES name for a (provider, model) pick (default model if None).

    Free/unlisted gateway models resolve to the provider name — its factory reads the
    chosen model from the env var, so pricing stays the provider's (conservative) table.
    """
    models = _PROVIDER_MODELS[provider]["models"]
    if model is None:
        return models[0][2] or provider
    for m, _c, fac in models:
        if m == model:
            return fac or provider
    return provider


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
    """set a role's model: /use <orchestration|extraction|parser> <provider> [model]"""
    from .. import config

    if not args:
        return "usage: /use <orchestration|extraction|parser> <provider> [model]"
    role = args[0]
    db = app.cost_meter.db_path

    if role == "parser":  # unchanged: parsers have no provider/model split
        name = args[1] if len(args) > 1 else ""
        if not name:
            return f"usage: /use parser <name>. options: {', '.join(PARSERS)}"
        if name not in PARSERS:
            return f"unknown parser: {name}. options: {', '.join(PARSERS)}"
        config.set_setting("parser_name", name, db_path=db)
        return f"parser → {name} (default for the next extract_paper)"

    if role not in ("orchestration", "orch", "extraction", "extract"):
        return f"unknown role: {role}. options: orchestration, extraction, parser"

    provs = _providers_for_role(role)
    if len(args) < 2:
        return f"usage: /use {role} <provider> [model]. providers: {', '.join(provs)}"
    provider = args[1]
    if provider not in provs:
        if provider in _PROVIDER_MODELS:  # real provider, wrong role
            return (f"'{provider}' can't drive the agent loop (OpenAI-compat → "
                    f"extraction-only). use /use extraction {provider}.")
        return f"unknown provider: {provider}. options: {', '.join(provs)}"

    spec = _PROVIDER_MODELS[provider]
    model = args[2] if len(args) > 2 else None
    known = [m for m, _c, _f in spec["models"]]
    if model is not None and model not in known and not spec.get("free"):
        return f"unknown {provider} model: {model}. options: {', '.join(known)}"

    if role in ("orchestration", "orch"):
        return _model(app, [_factory_for(provider, model)])  # constructs + hot-swaps + persists
    # extraction
    if "env" in spec:  # gateway providers carry the chosen model in an env var
        if model is not None:
            config.set_value(spec["env"], model)
        config.set_setting("extraction_model", provider, db_path=db)
        return f"extraction → {provider} ({model or 'default'}) — applies to the next extract_paper"
    factory = _factory_for(provider, model)  # deepseek/anthropic → a priced factory
    config.set_setting("extraction_model", factory, db_path=db)
    return f"extraction → {factory} (applies to the next extract_paper)"


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
    """reload a previous session: /resume [n] (n from the list; 1 = most recent)"""
    from ..session import load_session, prior_sessions

    cur = getattr(app.agent.session, "current_path", None)
    priors = prior_sessions(exclude=cur)
    if not priors:
        # No rotated prior sessions (first launch, or a stub/legacy single file) —
        # fall back to the agent's own loader so resume still works.
        msgs = _resume_trim(list(app.agent.session.load()))
        if not msgs:
            return "no prior session to resume."
        app.agent.messages = msgs
        return f"resumed {len(msgs)} message(s):\n{_resume_recap(msgs)}"
    idx = 0
    if args:
        try:
            idx = int(args[0]) - 1
        except ValueError:
            return "usage: /resume [n] — n is a number from the list (1 = most recent)"
    if not 0 <= idx < len(priors):
        return f"no session #{idx + 1}; there are {len(priors)} prior session(s). try /resume 1"
    msgs = _resume_trim(load_session(priors[idx]))
    if not msgs:
        return "that session has no resumable context."
    app.agent.messages = msgs  # restore context so the next turn continues with it
    return f"resumed session #{idx + 1} ({len(msgs)} message(s)):\n{_resume_recap(msgs)}"


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


def _clear(app, args: list[str]) -> str:
    """reset the agent's context — forget this conversation (budget/ledger untouched)"""
    app.agent.messages = []
    app.agent.last_usage = {}
    clear = getattr(app, "action_clear_log", None)
    if clear:
        clear()  # also wipe the on-screen log + its transcript mirror
    return "context cleared — the agent starts fresh."


def _transcript_md(msgs: list[dict]) -> str:
    """Render the agent's message history as readable markdown (B4)."""
    out = ["# palimpsest session transcript\n"]
    for m in msgs:
        role, content = m.get("role"), m.get("content")
        if role == "user" and isinstance(content, str):
            out.append(f"## ❯ you\n\n{content}\n")
        elif role == "assistant" and isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    out.append(f"## · palimpsest\n\n{b['text'].strip()}\n")
                elif b.get("type") == "tool_use":
                    inp = ", ".join(f"{k}={v}" for k, v in (b.get("input") or {}).items())
                    out.append(f"- 🔧 `{b.get('name')}({inp[:120]})`")
        elif role == "user" and isinstance(content, list):  # tool results
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = str(b.get("content", "")).strip().replace("\n", " ")
                    out.append(f"  ↳ {c[:200]}")
    return "\n".join(out) + "\n"


def _export(app, args: list[str]) -> str:
    """export the conversation to workspace/transcript-<ts>.md"""
    from datetime import datetime

    from ..policy import PolicyViolation, assert_writable, workspace_root

    msgs = list(app.agent.messages)  # the live context (always populated, no git gate)
    if not msgs:
        return "nothing to export yet."
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = workspace_root() / f"transcript-{ts}.md"
    try:
        path = assert_writable(str(out))  # same fence as write_file (defense in depth)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_transcript_md(msgs), encoding="utf-8")
    except (OSError, PolicyViolation) as exc:
        return f"export failed: {exc}"
    return f"exported {len(msgs)} message(s) → {out}"


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


def _view(app, args: list[str]) -> str:
    """open the provenance viewer for the last extraction (or /view <sha>)"""
    import webbrowser

    sha = args[0] if args else getattr(app, "_last_paper_sha", None)
    if not sha:
        return "no paper yet — run extract_paper first, or pass /view <sha>"
    url = f"http://localhost:8765/paper/{sha}"
    # The viewer is a separate process (supervised model — the TUI must not spawn
    # servers). Just point a browser at it; if it isn't up the browser shows a refused
    # connection, so name the start command.
    opened = webbrowser.open(url)
    tail = "" if opened else " (no browser launched — open it manually)"
    return f"opening {url}{tail}\nviewer not running? start it with:  pixi run viewer"


def _issues(app, args: list[str]) -> str:
    """list this session's tool errors, budget warnings, and exceptions"""
    issues = getattr(app.monitor, "issues", [])
    if not issues:
        return "no issues this session ✓"
    lines = [f"{len(issues)} issue(s) this session:"]
    for i in issues[-10:]:  # last 10 is plenty for a glance
        tool = f" [{i['tool']}]" if i.get("tool") else ""
        detail = str(i.get("detail", "")).replace("\n", " ")[:120]
        lines.append(f"  · {i.get('kind', '?')}{tool}: {detail}")
    return "\n".join(lines)


def _git(app, args: list[str]) -> str:
    """show the workspace action history — per-tool checkpoints + per-turn tags"""
    from .. import versioning

    hist = versioning.recent_history(20)
    if not hist:
        return "no workspace history yet — the agent hasn't changed any files."
    lines = ["workspace history (newest first):"]
    for h in hist:
        tag = f"   ⟵ {h['tag']}" if h["tag"] else ""
        lines.append(f"  {h['sha']}  {h['title']}{tag}")
    return "\n".join(lines)


# /review runs an AGENT turn (app.py submit intercepts it before dispatch and runs
# REVIEW_PROMPT), so the agent narrates the session and may consult `git`/
# workspace_status. The _review handler below is therefore UNREACHABLE — it exists
# only so /review carries a docstring for /help and the autocomplete menu.
REVIEW_PROMPT = (
    "Review this session for me. Summarize what you did: the files you created or "
    "changed in the workspace and why, the key findings, and anything still open or "
    "uncertain. Ground it in the actual per-action history — run "
    "`git log --oneline --decorate -20` (the workspace is a git repo) and/or use "
    "workspace_status — don't just recall from memory. Keep it concise and skimmable."
)


def _review(app, args: list[str]) -> str:
    """have the agent review and summarize this session's actions and changes"""
    return "（/review runs an agent turn — type it at the prompt in the TUI）"


SLASH_COMMANDS: dict[str, Callable] = {
    "help": _help,
    "quit": _quit,
    "budget": _budget,
    "cost": _cost,
    "model": _model,
    "use": _use,
    "theme": _theme,
    "resume": _resume,
    "clear": _clear,
    "export": _export,
    "config": _config,
    "undo": _undo,
    "view": _view,
    "issues": _issues,
    "git": _git,
    "review": _review,
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
    "help", "quit", "budget", "cost", "use", "theme", "resume", "clear", "export",
    "config", "undo", "view", "issues", "git", "review",
)

_PROVIDER_GLOSS = {
    "deepseek": "deepseek-v4-flash (cheap default)",
    "deepseek-pro": "deepseek-v4-pro (bigger)",
    "sonnet": "claude-sonnet-4-6 (fallback)",
    "haiku": "claude-haiku-4-5 (small/cheap)",
    "gemini": "OpenAI-compat (extraction only)",
    "openrouter": "OpenRouter gateway (extraction only; set OPENROUTER_MODEL)",
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
    "GEMINI_API_KEY": "Gemini key (extraction)",
    "OPENROUTER_API_KEY": "OpenRouter key (extraction gateway)",
    "OPENROUTER_MODEL": "OpenRouter model slug, e.g. openai/gpt-4o-mini",
    "RUNPOD_API_KEY": "RunPod key (GPU)",
    **{p["template_id_env"]: f"RunPod template id — {name} parser"
       for name, p in PARSERS.items()},
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
            return ("usage: /use <role> <provider> [model]",
                    [(r, _ROLE_GLOSS[r]) for r in ("orchestration", "extraction", "parser")])
        role = completed[0]
        if role == "parser":  # parsers have no provider/model split
            if pos == 1:
                return ("usage: /use parser <name>", [(n, _parser_gloss(n)) for n in PARSERS])
            return (None, [])
        if role not in ("orchestration", "orch", "extraction", "extract"):
            return (None, [])
        if pos == 1:  # pick a provider (loop-capable for orchestration; all for extraction)
            return (f"usage: /use {role} <provider> [model]",
                    [(p, _PROVIDER_MODELS[p]["desc"]) for p in _providers_for_role(role)])
        if pos == 2:  # pick a model under the chosen provider (id + comment)
            provider = completed[1]
            if provider in _PROVIDER_MODELS:
                return (f"usage: /use {role} {provider} <model>", _provider_model_rows(provider))
        return (None, [])
    if cmd == "resume":
        if pos == 0:
            from ..session import prior_sessions, session_recap

            sess = getattr(getattr(app, "agent", None), "session", None)
            cur = getattr(sess, "current_path", None)
            priors = prior_sessions(exclude=cur)
            if not priors:
                return ("no prior sessions to resume", [])
            rows = [(str(i + 1), session_recap(p)) for i, p in enumerate(priors[:9])]
            return ("usage: /resume <n> — pick a past session", rows)
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
