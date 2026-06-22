"""T26 / app-phase: the Scriptorium chat TUI — palimpsest's front door.

Chat-first: Rahat types natural language, the agent (DeepSeek by default, T50)
does the work. The visual identity is *Scriptorium* — ink-on-parchment, after the
project's namesake (a palimpsest is an overwritten manuscript whose older layer
shows through). The signature: the agent's reply is the bright top layer; its tool
work (calls + results) renders as the faded sepia underwriting beneath it.

Layout: a title line on top, a scrolling column of per-message widgets (user lines,
dim tool traces, markdown-rendered agent replies), and a framed input above a quiet
footer status line (the three model roles + live €-spend). ``/``-prefixed input is
routed to the T27 slash dispatcher (see slash.py).

Concurrency: ``agent.run()`` makes a multi-second network call and writes to the
CostMeter, so it runs in a Textual thread worker to keep the UI live. Only one
request runs at a time — the input is disabled while in flight — so the CostMeter
(opened ``check_same_thread=False``) is never touched concurrently. See T26 in
DEVIATIONS.md. View updates always hop to the main thread via ``call_from_thread``.
"""

from __future__ import annotations

import threading

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Markdown, Static

from ..agent import Agent, build_agent
from ..cost import CostMeter
from ..monitor import SessionMonitor
from .slash import dispatch
from .themes import DEFAULT_THEME, THEMES

_TRUNCATE = 200  # tool-result snippet cap (a long blob shouldn't flood the log)


class PalimpsestApp(App):
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear log"),
        ("escape", "cancel_turn", "Stop"),
    ]

    def __init__(self, agent: Agent, cost_meter: CostMeter) -> None:
        # Dependency-injected (mirrors extract/pipeline) so tests feed a stub agent
        # + temp CostMeter. main() wires the real DeepSeek-backed agent.
        super().__init__()
        self.agent = agent
        self.cost_meter = cost_meter
        # Plain-text mirror of what's on screen, in order. The view is a tree of
        # widgets (hard to read back), so every appended message also lands here as
        # (role, text) — the stable seam tests assert against.
        self.transcript: list[tuple[str, str]] = []
        # T63: subscribe to the agent's tool events so the supervisor sees the loop
        # live. The agent fires these on the worker thread (see below).
        self.agent.on_event = self._on_agent_event
        # Capture this session to a durable demo log (echo off — a print() would
        # corrupt the Textual screen). Same gitignored dir as session.jsonl.
        self.monitor = SessionMonitor(echo=False)
        # T65: one cancel event shared with the agent. Esc sets it (main thread); the
        # agent reads it at each turn boundary (worker thread).
        self.cancel_event = threading.Event()
        self.agent.cancel_event = self.cancel_event

    def compose(self) -> ComposeResult:
        yield Static("palimpsest", id="topbar")
        yield VerticalScroll(id="log")
        with Vertical(id="dockbottom"):
            yield Input(placeholder="message palimpsest…   ( / for commands )", id="prompt")
            yield Static(self._status_text(), id="status")

    def on_mount(self) -> None:
        from .. import config

        for theme in THEMES.values():
            self.register_theme(theme)
        name = config.get_setting("ui_theme", DEFAULT_THEME, db_path=self.cost_meter.db_path)
        self.theme = name if name in THEMES else DEFAULT_THEME  # guard a stale setting
        self._refresh_topbar()
        prompt = self.query_one("#prompt", Input)
        prompt.border_title = "ask"
        prompt.border_subtitle = "enter ↵ to send · esc to stop"
        prompt.focus()

    def _refresh_topbar(self) -> None:
        self.query_one("#topbar", Static).update(f"palimpsest · {self.theme}")

    # status footer ----------------------------------------------------------
    def _status_text(self) -> str:
        from .. import config

        db = self.cost_meter.db_path
        orch = config.get_setting("orchestration_model", "deepseek", db_path=db)
        extr = config.get_setting("extraction_model", "deepseek", db_path=db)
        parser = config.get_setting("parser_name", "mineru", db_path=db)
        spent, cap = self.cost_meter.total_eur(), self.cost_meter.cap
        return f"{orch} · extract:{extr} · parse:{parser}    €{spent:.2f} / €{cap:.0f}    /help"

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    # message rendering ------------------------------------------------------
    def _emit(self, role: str, text: str, *, widget=None, renderable=None, classes: str = "") -> None:
        """Mount one message widget into the log and mirror it into the transcript.

        Always runs on the main thread (called directly from event handlers, or via
        call_from_thread from the worker). ``widget`` mounts a prebuilt widget (e.g. a
        theme-aware Markdown for replies); else ``renderable``/``text`` go in a Static.
        ``text`` is always the plain mirror recorded for the transcript seam.
        """
        self.transcript.append((role, text))
        if self._exit:  # quitting (/quit): skip the view mount — write-after-exit must not crash
            return
        w = widget if widget is not None else Static(
            renderable if renderable is not None else text, classes=classes
        )
        log = self.query_one("#log", VerticalScroll)
        log.mount(w)
        log.scroll_end(animate=False)

    # chat loop --------------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        self._emit("user", text, renderable=Text(f"❯ {text}", style="bold"), classes="msg-user")

        if text.startswith("/"):
            self._emit("system", dispatch(self, text), classes="trace")  # T27: before the agent
            self._set_status(self._status_text())  # a /use or /budget may have changed it
            return

        # Clear any stale cancel left set by a late Esc as the previous turn ended
        # (input was still disabled then) — otherwise this fresh run would cancel
        # itself at turn 0. Safe on the main thread (T65). After this, an Esc sets the
        # flag for the worker to observe at its next turn boundary.
        self.cancel_event.clear()
        # Disable the input for the duration of the call: this guarantees a single
        # request in flight, so the CostMeter is never written concurrently.
        event.input.disabled = True
        self._set_status("· working…")
        self._run_agent(text)

    @work(thread=True)
    def _run_agent(self, text: str) -> None:
        try:
            # Route through the monitor so each TUI turn records its euro delta + any
            # exception/budget refusal to the demo log (monitor.run catches its own
            # failures and returns an [error]/[budget] string, never raising).
            reply = self.monitor.run(self.agent, text)
        except Exception as exc:  # noqa: BLE001 — backstop: surface any failure into the chat
            reply = f"error: {exc}"
        # Hop back to the main thread to touch widgets + the status bar. This also acts
        # as the sync barrier that keeps CostMeter access non-concurrent.
        self.call_from_thread(self._show_reply, reply)

    # live tool trace (T63) -------------------------------------------------
    def _on_agent_event(self, event: dict) -> None:
        # Fires on the worker thread (inside agent.run). Capture to the demo log here
        # (single-writer: the agent loop is serial and this is the only writer), then
        # hop to the main thread to touch the widget — same marshalling the reply uses.
        self.monitor.observe(event)
        self.call_from_thread(self._show_event, event)

    def _show_event(self, event: dict) -> None:
        if event["type"] == "tool_call":
            args = ", ".join(str(v) for v in (event["input"] or {}).values())
            self._emit("trace", f"→ {event['name']}({args})", classes="trace")
        else:
            content = str(event["content"])
            snippet = content if len(content) <= _TRUNCATE else content[:_TRUNCATE] + "…"
            marker = "✗" if event.get("is_error") else "←"
            self._emit(
                "trace", f"{marker} {snippet}",
                classes="trace-error" if event.get("is_error") else "trace",
            )

    def _show_reply(self, reply: str) -> None:
        # The reply is the bright top layer — render it through Textual's theme-aware
        # Markdown widget (headings/lists/code take the Scriptorium palette, not Rich's
        # default red/cyan) over the faded tool traces above it.
        self._emit("agent", reply, widget=Markdown(reply, classes="msg-agent"))
        self._set_status(self._status_text())
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = False
        prompt.focus()

    def action_clear_log(self) -> None:
        self.query_one("#log", VerticalScroll).remove_children()
        self.transcript.clear()

    def action_cancel_turn(self) -> None:
        # T65: request cancellation of the turn in flight. The input is disabled
        # exactly while the agent worker is running, so an enabled input means nothing
        # to cancel — ignore (and don't leave the flag set for the next run).
        if not self.query_one("#prompt", Input).disabled:
            return
        self.cancel_event.set()
        self._emit("trace", "cancelling… (stops at the next step)", classes="trace")


def main() -> None:
    from ..config import ensure_role_credentials, load
    from ..versioning import ensure_repo

    load()
    ensure_repo()
    # Prompt (terminal getpass) for a missing provider key before the Textual loop
    # takes the screen — so no modal is needed and the agent never invents secrets.
    # Covers both the orchestration and extraction providers (app phase).
    ensure_role_credentials()
    # Share one CostMeter between the agent and the status bar (same wiring as the
    # CLI, via build_agent); the bar reads the same on-disk ledger the agent meters.
    cost_meter = CostMeter("palimpsest.db")
    agent = build_agent(cost_meter=cost_meter)
    PalimpsestApp(agent=agent, cost_meter=cost_meter).run()
