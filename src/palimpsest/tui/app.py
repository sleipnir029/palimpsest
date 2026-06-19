"""T26: Textual chat TUI — palimpsest's user-facing front door.

Chat-first: Rahat types natural language, the agent (DeepSeek by default, T50)
does the work. One screen — a cost-meter bar, a scrollable message log, an input
box. ``/``-prefixed input is routed to the T27 slash dispatcher (see slash.py).

Concurrency: ``agent.run()`` makes a multi-second network call and writes to the
CostMeter, so it runs in a Textual thread worker to keep the UI live. Only one
request runs at a time — the input is disabled while in flight — so the CostMeter
(opened ``check_same_thread=False``) is never touched concurrently. See T26 in
DEVIATIONS.md.
"""

from __future__ import annotations

import threading

from rich.markup import escape
from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Static

from ..agent import Agent, build_agent
from ..cost import CostMeter
from ..monitor import SessionMonitor
from .slash import dispatch


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
        # T63: subscribe to the agent's tool events so the supervisor sees the
        # loop live. The agent fires these on the worker thread (see below).
        self.agent.on_event = self._on_agent_event
        # Also capture this session to a durable demo log (echo off — a print()
        # would corrupt the Textual screen). Same gitignored dir as session.jsonl.
        self.monitor = SessionMonitor(echo=False)
        # T65: one cancel event shared with the agent. Esc sets it (on the main
        # thread); the agent reads it at each turn boundary (on the worker thread).
        # threading.Event is the right primitive for this cross-thread one-way flag.
        self.cancel_event = threading.Event()
        self.agent.cancel_event = self.cancel_event

    def compose(self) -> ComposeResult:
        yield Static(self._cost_text(), id="costbar")
        yield RichLog(id="log", markup=True, wrap=True)
        yield Input(
            placeholder="Ask palimpsest…  (/ commands · Ctrl+Q quit · Ctrl+L clear)",
            id="prompt",
        )

    def on_mount(self) -> None:
        self.query_one("#prompt", Input).focus()

    # cost bar ---------------------------------------------------------------
    def _cost_text(self) -> str:
        return f"€{self.cost_meter.total_eur():.2f} / €{self.cost_meter.cap:.0f}"

    def _refresh_cost(self) -> None:
        self.query_one("#costbar", Static).update(self._cost_text())

    # chat loop --------------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        log = self.query_one("#log", RichLog)
        log.write(f"[bold]you[/] {escape(text)}")  # escape: typed [..] isn't markup
        event.input.value = ""

        if text.startswith("/"):
            log.write(escape(dispatch(self, text)))  # T27: intercepted before the agent
            return

        # Clear any stale cancel left set by a late Esc as the previous turn ended
        # (input was still disabled then) — otherwise this fresh run would cancel
        # itself at turn 0. Safe on the main thread (where Esc is also handled), so
        # the clear can't be lost to an interleaving keypress (T65). After this, an
        # Esc sets the flag for the worker to observe at its next turn boundary.
        self.cancel_event.clear()
        # Disable the input for the duration of the call: this is what guarantees a
        # single request in flight, so the CostMeter is never written concurrently.
        event.input.disabled = True
        log.write("[dim]…thinking[/]")
        self._run_agent(text)

    @work(thread=True)
    def _run_agent(self, text: str) -> None:
        try:
            # Route through the monitor so each TUI turn records its euro delta +
            # any exception/budget refusal to the demo log (monitor.run catches its
            # own failures and returns an [error]/[budget] string, never raising).
            reply = self.monitor.run(self.agent, text)
        except Exception as exc:  # noqa: BLE001 — backstop: surface any failure into the chat
            reply = f"error: {exc}"
        # Hop back to the main thread to touch widgets + the cost bar. This also
        # acts as the sync barrier that keeps CostMeter access non-concurrent.
        self.call_from_thread(self._show_reply, reply)

    # live tool trace (T63) -------------------------------------------------
    def _on_agent_event(self, event: dict) -> None:
        # Fires on the worker thread (inside agent.run). Capture to the demo log
        # here (single-writer: the agent loop is serial and this is the only writer,
        # so no lock is needed), then hop to the main thread to touch the widget —
        # same marshalling the reply uses, so no widget is touched off-thread.
        self.monitor.observe(event)
        self.call_from_thread(self._show_event, event)

    def _show_event(self, event: dict) -> None:
        log = self.query_one("#log", RichLog)
        if event["type"] == "tool_call":
            args = ", ".join(str(v) for v in (event["input"] or {}).values())
            log.write(f"[dim]→ {event['name']}({escape(args)})[/]")
        else:
            content = str(event["content"])
            snippet = content if len(content) <= 200 else content[:200] + "…"
            marker = "✗" if event.get("is_error") else "←"
            log.write(f"[dim]{marker} {escape(snippet)}[/]")

    def _show_reply(self, reply: str) -> None:
        self.query_one("#log", RichLog).write(f"[bold green]palimpsest[/] {escape(reply)}")
        self._refresh_cost()
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = False
        prompt.focus()

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    def action_cancel_turn(self) -> None:
        # T65: request cancellation of the turn in flight. The input is disabled
        # exactly while the agent worker is running, so an enabled input means
        # nothing to cancel — ignore (and don't leave the flag set for the next run).
        if not self.query_one("#prompt", Input).disabled:
            return
        self.cancel_event.set()
        self.query_one("#log", RichLog).write("[dim]cancelling… (stops at the next step)[/]")


def main() -> None:
    from ..config import ensure_llm_credentials, load
    from ..versioning import ensure_repo

    load()
    ensure_repo()
    # Prompt (terminal getpass) for a missing provider key before the Textual loop
    # takes the screen — so no modal is needed and the agent never invents secrets.
    ensure_llm_credentials()
    # Share one CostMeter between the agent and the cost bar (same wiring as the
    # CLI, via build_agent); the bar reads the same on-disk ledger the agent meters.
    cost_meter = CostMeter("palimpsest.db")
    agent = build_agent(cost_meter=cost_meter)
    PalimpsestApp(agent=agent, cost_meter=cost_meter).run()
