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
import time

from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Collapsible, Markdown, Static, TextArea

from ..agent import Agent, build_agent
from ..cost import CostMeter
from ..monitor import SessionMonitor
from .slash import dispatch, menu_for
from .themes import DEFAULT_THEME, THEMES

_TRUNCATE = 200  # tool-result snippet cap (a long blob shouldn't flood the log)
_FULL_TRUNCATE = 4000  # higher cap for supervision-relevant tools (bash, extract_paper)


def _diff_text(content: str) -> Text:
    """Color an ``edited <path>\\n<unified diff>`` blob: +adds green, -dels red (A4)."""
    out = Text()
    for i, line in enumerate(content.splitlines()):
        if i == 0:
            out.append(line + "\n")  # the "edited <path>" header
        elif line.startswith("+") and not line.startswith("+++"):
            out.append(line + "\n", style="green")
        elif line.startswith("-") and not line.startswith("---"):
            out.append(line + "\n", style="red")
        else:
            out.append(line + "\n", style="dim")
    return out


class PromptArea(TextArea):
    """Multi-line composer (C1): Enter submits, Ctrl+J inserts a newline.

    Textual's TextArea maps Enter to a newline insert; we intercept it to submit
    (like the old single-line Input) and move newline-insertion to Ctrl+J.
    ponytail: Shift+Enter is the familiar gesture, but most terminals can't
    distinguish it from Enter — Ctrl+J is the reliable newline key. We bind both
    and use whichever the terminal actually delivers.
    """

    class Submitted(Message):
        """Posted when the user presses Enter; carries the composer's full text."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def _menu_is_open(self) -> bool:
        check = getattr(self.app, "_menu_open", None)
        return bool(check and check())

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted(self.text))
            return
        if event.key == "escape":
            # TextArea's default escape handler calls screen.focus_next(), which steals
            # focus from the composer and leaves the app feeling frozen. Intercept it:
            # route to the app's cancel/menu-close action and KEEP focus here.
            event.stop()
            event.prevent_default()
            self.app.action_cancel_turn()
            return
        if event.key in ("ctrl+j", "shift+enter"):
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        # up/down drive the autocomplete menu / input history, but only when the menu
        # is open or the cursor is at the composer's top/bottom edge — otherwise they
        # move the cursor between lines like a normal multi-line editor.
        if event.key in ("up", "down"):
            row = self.cursor_location[0]
            at_edge = (event.key == "up" and row == 0) or (
                event.key == "down" and row == self.text.count("\n")
            )
            if self._menu_is_open() or at_edge:
                event.stop()
                event.prevent_default()
                action = self.app.action_menu_up if event.key == "up" else self.app.action_menu_down
                action()
                return
        await super()._on_key(event)


class PalimpsestApp(App):
    CSS_PATH = "styles.tcss"
    # ponytail: app-level mouse selection off — dodges a Textual 8.2.7 assert that
    # crashes on MouseDown over a markdown table mid-rebuild (screen.py:1896). Terminal-
    # native selection (Option-drag macOS, Shift elsewhere) still copies text.
    ALLOW_SELECT = False
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear log"),
        ("escape", "cancel_turn", "Stop"),
        # Slash-command autocomplete: these act only while the menu is open (no-ops
        # otherwise), so the single-line input loses nothing by binding them. tab is
        # priority so it preempts Textual's built-in focus-navigation handler.
        Binding("up", "menu_up", "Menu up", show=False),
        Binding("down", "menu_down", "Menu down", show=False),
        Binding("tab", "menu_complete", "Complete", priority=True, show=False),
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
        # Streaming reply state (A1): the agent fires assistant_delta events as text
        # arrives; the deltas land in one live Markdown widget. None = no reply in
        # flight. The buffer is mirrored to the transcript once, on seal.
        self._stream_widget: Markdown | None = None
        self._stream_buf = ""
        # Render throttle (A1): Markdown.update re-parses the whole buffer, so calling it
        # per-delta is O(n²) and freezes the UI on long replies. Render at most ~10 Hz;
        # _seal_stream does the final flush so nothing is lost. monotonic clock, main
        # thread only (deltas arrive via call_from_thread).
        self._stream_last_render = 0.0
        # The tool trace renders one collapsible per call: mounted (title "… running…")
        # when the call fires, its title+body filled when the result arrives. Holds the
        # in-flight (collapsible, body, name, args) between those two events; None = idle.
        self._pending_tool: tuple[Collapsible, Static, str, str] | None = None
        # Input history (A5): submitted lines, recalled with up/down when the
        # autocomplete menu is closed. _history_idx is the cursor (None = not recalling).
        self._history: list[str] = []
        self._history_idx: int | None = None
        # Slash-command autocomplete state. `_menu` holds the selectable tokens
        # (command names in command mode, argument values in arg mode); `_menu_glosses`
        # is the parallel note per row; `_menu_usage` an optional header line. Empty
        # `_menu` + None `_menu_usage` == menu closed. `_menu_prefix` is prepended on
        # Tab-completion; `_menu_arg` flips Enter from "complete" to "run the line".
        self._menu: list[str] = []
        self._menu_idx = 0
        self._menu_glosses: list[str] = []
        self._menu_usage: str | None = None
        self._menu_prefix = "/"
        self._menu_arg = False
        self._menu_label_slash = True
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
            yield Static(id="cmdmenu")  # slash-command autocomplete; shown on demand
            yield PromptArea(id="prompt", soft_wrap=True, show_line_numbers=False)
            yield Static(self._status_text(), id="status")

    def on_mount(self) -> None:
        from .. import config

        for theme in THEMES.values():
            self.register_theme(theme)
        name = config.get_setting("ui_theme", DEFAULT_THEME, db_path=self.cost_meter.db_path)
        self.theme = name if name in THEMES else DEFAULT_THEME  # guard a stale setting
        self._refresh_topbar()
        self.query_one("#cmdmenu", Static).display = False
        # A quiet welcome so the empty screen orients rather than stares back. Mounted
        # directly (not via _emit) so it stays out of the transcript and scrolls away
        # naturally once the conversation starts.
        self.query_one("#log", VerticalScroll).mount(
            Static(
                Text.assemble(
                    ("Ask a question, or type ", "dim"),
                    ("/", "bold"),
                    (" for commands.   e.g. ", "dim"),
                    ("extract papers/<file>.pdf", "italic"),
                ),
                classes="welcome",
            )
        )
        prompt = self.query_one("#prompt", PromptArea)
        prompt.border_title = "ask"
        prompt.border_subtitle = "enter ↵ send · ctrl+j ⏎ newline · tab ⇥ complete · esc stop"
        prompt.focus()
        # Seed up-arrow history from recent sessions so past prompts recall across
        # launches (A5 / cross-session). Best-effort: empty outside a workspace repo.
        try:
            from ..session import recent_inputs

            self._history = recent_inputs()
        except Exception:  # noqa: BLE001 — history is a convenience, never fatal
            self._history = []

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
        # ctx: prompt size sent on the last turn = the live context the agent carries
        # (A3). Reuses agent.last_usage — no tokenizer dependency. Hidden until the
        # first turn records a usage block.
        toks = (getattr(self.agent, "last_usage", None) or {}).get("input_tokens", 0)
        ctx = f"    ctx ~{toks / 1000:.1f}k" if toks else ""
        return f"{orch} · extract:{extr} · parse:{parser}    €{spent:.2f} / €{cap:.0f}{ctx}    /help"

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    # slash autocomplete -----------------------------------------------------
    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        text = event.text_area.text
        # While browsing history, a recalled line — even a slash command — must NOT pop
        # the autocomplete menu, or up/down would switch to menu nav and break browsing.
        # Detect our own recall: the text equals the current history entry. A real edit
        # (text differs) exits browse mode and syncs the menu normally.
        if (
            self._history_idx is not None
            and 0 <= self._history_idx < len(self._history)
            and text == self._history[self._history_idx]
        ):
            return
        self._history_idx = None
        self._sync_menu(text)

    def _sync_menu(self, value: str) -> None:
        """Refresh the autocomplete from the input value (command or argument mode)."""
        widget = self.query_one("#cmdmenu", Static)
        menu = menu_for(self, value)
        if menu is None:
            self._close_menu()
            return
        new_menu = [t for t, _ in menu.rows]
        # Keep the highlight only while the same rows persist; a changed row set
        # (e.g. command list → a different arg list) resets it to the top so the
        # selection never lands on a semantically different row.
        self._menu_idx = (
            min(self._menu_idx, max(0, len(new_menu) - 1))
            if new_menu == self._menu else 0
        )
        self._menu = new_menu
        self._menu_glosses = [g for _, g in menu.rows]
        self._menu_usage = menu.usage
        self._menu_prefix = menu.prefix
        self._menu_label_slash = menu.label_slash
        self._menu_arg = not menu.label_slash
        widget.update(self._render_menu())
        widget.display = True

    def _render_menu(self) -> Text:
        out = Text()
        if self._menu_usage:  # a usage header (arg mode) sits above the value rows
            out.append(f"{self._menu_usage}\n", style="dim")
        for i, tok in enumerate(self._menu):
            gloss = self._menu_glosses[i] if i < len(self._menu_glosses) else ""
            selected = i == self._menu_idx
            label = f"/{tok}" if self._menu_label_slash else tok
            out.append(f"{'❯' if selected else ' '} {label}", style="bold" if selected else "")
            out.append(f"   {gloss}\n", style="" if selected else "dim")
        return out

    def _menu_open(self) -> bool:
        return bool(self._menu) or self._menu_usage is not None

    def _close_menu(self) -> None:
        self._menu = []
        self._menu_idx = 0
        self._menu_glosses = []
        self._menu_usage = None
        self._menu_prefix = "/"
        self._menu_arg = False
        self._menu_label_slash = True
        self.query_one("#cmdmenu", Static).display = False

    def action_menu_down(self) -> None:
        if self._menu:
            self._menu_idx = (self._menu_idx + 1) % len(self._menu)
            self.query_one("#cmdmenu", Static).update(self._render_menu())
            return
        self._history_recall(+1)  # menu closed → newer history (A5)

    def action_menu_up(self) -> None:
        if self._menu:
            self._menu_idx = (self._menu_idx - 1) % len(self._menu)
            self.query_one("#cmdmenu", Static).update(self._render_menu())
            return
        self._history_recall(-1)  # menu closed → older history (A5)

    def _history_recall(self, direction: int) -> None:
        """Walk input history into the prompt (-1 older, +1 newer); past the newest
        clears the line. No-op while the agent is running (input disabled)."""
        prompt = self.query_one("#prompt", PromptArea)
        if prompt.disabled or not self._history:
            return
        if self._history_idx is None:
            if direction > 0:
                return  # already at the live (empty) line
            self._history_idx = len(self._history) - 1
        else:
            self._history_idx += direction
            if self._history_idx >= len(self._history):
                self._history_idx = None
                prompt.text = ""
                return
            self._history_idx = max(0, self._history_idx)
        prompt.text = self._history[self._history_idx]
        prompt.move_cursor(prompt.document.end)

    def action_menu_complete(self) -> None:
        """Accept the highlighted token (command or argument value) into the input."""
        if not self._menu:
            return
        tok = self._menu[self._menu_idx]
        prompt = self.query_one("#prompt", PromptArea)
        prompt.text = f"{self._menu_prefix}{tok} "
        prompt.move_cursor(prompt.document.end)
        self._close_menu()

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
    def on_prompt_area_submitted(self, event: "PromptArea.Submitted") -> None:
        # Enter while the autocomplete menu is open. In argument mode, Enter runs the
        # line as typed (Tab is what completes a value). In command mode, if the command
        # is fully typed (value == "/cmd") run it; otherwise accept the highlighted
        # command into the input (Claude-Code style) and wait for the user to type args.
        if self._menu_open():
            if self._menu_arg:
                self._close_menu()  # fall through and dispatch the typed line
            else:
                selected = self._menu[self._menu_idx]
                if event.value.strip() != f"/{selected}":
                    self.action_menu_complete()
                    return
                self._close_menu()  # fully typed → fall through and dispatch it
        text = event.value.strip()
        prompt = self.query_one("#prompt", PromptArea)
        if not text:
            return
        prompt.text = ""
        # Record for up/down recall (A5): every submitted line incl. slash commands,
        # skipping consecutive dupes. Reset the recall cursor.
        if not self._history or self._history[-1] != text:
            self._history.append(text)
        self._history_idx = None
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
        prompt.disabled = True
        self._set_status("· working…")
        self._stream_widget = None  # fresh reply: don't append to a stale widget
        self._stream_buf = ""
        self._pending_tool = None  # no half-open tool collapsible carried across turns
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
        # Fires on the worker thread (inside agent.run). The demo monitor only models
        # tool_call/tool_result — keep streaming/stage events away from it (it would
        # mis-time them as tool results). Then hop to the main thread for the widgets.
        if event.get("type") in ("tool_call", "tool_result"):
            self.monitor.observe(event)
        self.call_from_thread(self._show_event, event)

    def _show_event(self, event: dict) -> None:
        # Runs on the main thread (via call_from_thread). A render glitch here would
        # reach Textual's dispatcher and panic the whole app, so it's the one main-thread
        # path left to guard (the worker + monitor already are). Degrade to a visible note.
        try:
            self._render_event(event)
        except Exception as exc:  # noqa: BLE001 — never let a render error tear the app down
            self.monitor.issues.append({"kind": "exception", "detail": f"render: {exc!r}"})
            try:
                self._emit("trace", f"⚠ render error: {exc}", classes="trace-error")
            except Exception:  # noqa: BLE001 — last resort: swallow rather than re-raise
                pass

    def _render_event(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "assistant_delta":  # A1: streamed reply text
            self._stream_append(event["text"])
            return
        if etype == "stage":  # B1: pipeline progress under the active tool
            self._emit("trace", f"· {event['text']}", classes="trace")
            return
        if etype == "tool_call":
            self._seal_stream()  # any streamed text precedes this call — finalize it
            name = event["name"]
            args = ", ".join(str(v) for v in (event["input"] or {}).values())
            # One collapsible per tool: a tidy title now (args clipped), the body filled
            # when the result lands. Mirror the full "→ name(args)" line to the transcript
            # seam (tests assert label + ordering) via _emit, which also mounts the widget.
            args_disp = args if len(args) <= 60 else args[:60] + "…"
            body = Static("")
            col = Collapsible(body, title=f"{name}({args_disp}) — running…", collapsed=True, classes="trace")
            self._pending_tool = (col, body, name, args_disp)
            self._emit("trace", f"→ {name}({args})", widget=col)
            return

        # tool_result: summarise into the collapsible title, full detail in its body.
        name = event.get("name")
        content = str(event["content"])
        is_error = bool(event.get("is_error"))
        if name == "edit_file" and content.startswith("edited "):
            # A4: the unified diff (with +/- colouring) is the detail worth keeping.
            body_render, summary, mirror = _diff_text(content), "edited", content
        else:
            # A4/B2: bash + extract_paper are supervision-relevant (the command run, the
            # graph mutation) — keep their full output; clip everything else.
            cap = _FULL_TRUNCATE if name in ("bash", "extract_paper") else _TRUNCATE
            snippet = content if len(content) <= cap else content[:cap] + "…"
            marker = "✗" if is_error else "←"
            mirror = f"{marker} {snippet}"  # unchanged transcript seam (truncation/marker)
            nlines = content.count("\n") + 1 if content.strip() else 0
            summary = "error" if is_error else (f"{nlines} lines" if nlines else "ok")
            body_render = Text(snippet, style="red") if is_error else snippet

        cls = "trace-error" if is_error else "trace"
        if self._pending_tool is not None:  # fill the collapsible from the matching call
            col, body, cname, cargs = self._pending_tool
            col.title = f"{cname}({cargs}) — {summary}"
            if is_error:
                col.add_class("trace-error")
            body.update(body_render)
            self._pending_tool = None
            self.transcript.append(("trace", mirror))  # widget already mounted; mirror only
        else:  # a result with no preceding call (e.g. a direct error) — mount fresh
            col = Collapsible(Static(body_render), title=f"{name or 'tool'} — {summary}", collapsed=True, classes=cls)
            self._emit("trace", mirror, widget=col)

    def _stream_append(self, delta: str) -> None:
        """Append a streamed text delta to the live reply widget (A1), mounting it on
        the first delta. The buffer accumulates every delta, but the costly
        Markdown.update render is throttled to ~10 Hz (see _stream_last_render) so a
        long reply doesn't re-parse the whole buffer per token and freeze the UI.
        _seal_stream guarantees the final render. Not mirrored to the transcript until
        seal."""
        if self._stream_widget is None:
            self._stream_widget = Markdown(classes="msg-agent")
            self.query_one("#log", VerticalScroll).mount(self._stream_widget)
            self._stream_last_render = 0.0  # force a render on the first delta
        self._stream_buf += delta
        now = time.monotonic()
        if now - self._stream_last_render < 0.1:
            return  # coalesce: a later delta (or seal) will render the accrued buffer
        self._stream_last_render = now
        self._stream_widget.update(self._stream_buf)
        self.query_one("#log", VerticalScroll).scroll_end(animate=False)

    def _seal_stream(self) -> None:
        """Finalize the live reply widget: flush the last accrued deltas (the throttle
        may have skipped them), mirror its text to the transcript once, and stop
        appending (a later turn's text starts a fresh widget)."""
        if self._stream_widget is None:
            return
        self._stream_widget.update(self._stream_buf)  # final flush: catch throttled tail
        self.transcript.append(("agent", self._stream_buf))
        self._stream_widget = None
        self._stream_buf = ""

    def _show_reply(self, reply: str) -> None:
        # Seal any live streamed text first — it's already on screen. A normally
        # streamed reply needs nothing more (don't re-mount resp.text: it can differ
        # from the deltas by trailing whitespace and would double-render).
        had_stream = self._stream_widget is not None
        self._seal_stream()
        if reply.startswith(("[cancelled]", "[error]", "[budget]")):
            # Control strings from the worker/monitor: a quiet note (it sits under the
            # partial reply when Esc landed mid-stream, so the user sees both).
            self._emit("trace", reply, classes="trace")
        elif not had_stream and reply:
            # Nothing streamed (non-streaming fallback): mount as the bright reply.
            self._emit("agent", reply, widget=Markdown(reply, classes="msg-agent"))
        self._set_status(self._status_text())
        prompt = self.query_one("#prompt", PromptArea)
        prompt.disabled = False
        prompt.focus()

    def action_clear_log(self) -> None:
        self.query_one("#log", VerticalScroll).remove_children()
        self.transcript.clear()
        # A clear mid-stream must drop the live widget reference (it was just removed)
        # so the next delta starts a fresh one instead of updating a detached widget.
        self._stream_widget = None
        self._stream_buf = ""
        self._pending_tool = None  # the removed children include any open tool collapsible

    def action_cancel_turn(self) -> None:
        # Esc first dismisses an open autocomplete menu (doesn't cancel the turn).
        if self._menu:
            self._close_menu()
            return
        # T65: request cancellation of the turn in flight. The input is disabled
        # exactly while the agent worker is running, so an enabled input means nothing
        # to cancel — ignore (and don't leave the flag set for the next run).
        if not self.query_one("#prompt", PromptArea).disabled:
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
