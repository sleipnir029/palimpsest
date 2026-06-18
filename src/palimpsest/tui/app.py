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

from dotenv import load_dotenv
from rich.markup import escape
from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Static

from ..agent import Agent, build_agent
from ..cost import CostMeter
from .slash import dispatch


class PalimpsestApp(App):
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear log"),
    ]

    def __init__(self, agent: Agent, cost_meter: CostMeter) -> None:
        # Dependency-injected (mirrors extract/pipeline) so tests feed a stub agent
        # + temp CostMeter. main() wires the real DeepSeek-backed agent.
        super().__init__()
        self.agent = agent
        self.cost_meter = cost_meter

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

        # Disable the input for the duration of the call: this is what guarantees a
        # single request in flight, so the CostMeter is never written concurrently.
        event.input.disabled = True
        log.write("[dim]…thinking[/]")
        self._run_agent(text)

    @work(thread=True)
    def _run_agent(self, text: str) -> None:
        try:
            reply = self.agent.run(text)
        except Exception as exc:  # noqa: BLE001 — surface any failure into the chat
            reply = f"error: {exc}"
        # Hop back to the main thread to touch widgets + the cost bar. This also
        # acts as the sync barrier that keeps CostMeter access non-concurrent.
        self.call_from_thread(self._show_reply, reply)

    def _show_reply(self, reply: str) -> None:
        self.query_one("#log", RichLog).write(f"[bold green]palimpsest[/] {escape(reply)}")
        self._refresh_cost()
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = False
        prompt.focus()

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()


def main() -> None:
    load_dotenv()
    # Init the workspace git repo so every agent action is logged + undoable.
    from ..versioning import ensure_repo

    ensure_repo()
    # Share one CostMeter between the agent and the cost bar (same wiring as the
    # CLI, via build_agent); the bar reads the same on-disk ledger the agent meters.
    cost_meter = CostMeter("palimpsest.db")
    agent = build_agent(cost_meter=cost_meter)
    PalimpsestApp(agent=agent, cost_meter=cost_meter).run()
