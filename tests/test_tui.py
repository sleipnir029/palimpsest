"""T26 smoke test: PalimpsestApp mounts and the threaded reply path runs offline.

No network, no DEEPSEEK_API_KEY: a stub agent stands in for the real Agent. No
pytest-asyncio in the env, so the async Textual pilot is driven via asyncio.run().
This exercises the real path (submit → thread worker → call_from_thread →
re-enable input), not just construction.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Static

from palimpsest.cost import CostMeter
from palimpsest.tui.app import PalimpsestApp, PromptArea
from palimpsest.tui.slash import menu_for


def _text(app: PalimpsestApp) -> str:
    """The on-screen transcript as plain text — the stable seam for assertions.

    The view is a tree of per-message widgets (Scriptorium rebuild); the app mirrors
    every appended message into ``app.transcript`` as (role, text) in order, so tests
    assert content + ordering without reaching into widget internals."""
    return "\n".join(t for _role, t in app.transcript)


@pytest.fixture(autouse=True)
def _isolate_workspace(tmp_path, monkeypatch):
    """Point the workspace at a throwaway dir so the app's SessionMonitor writes its
    demo log into tmp, never the real ./workspace/.palimpsest (test isolation —
    mirrors test_session/test_versioning). Without this, constructing PalimpsestApp
    pollutes the real workspace and can trip a live monitor with a fixture event."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))


class _StubAgent:
    """Stand-in for Agent: no network. Records the message and bills the meter
    like the real Agent does, so the cost-bar update can be asserted."""

    def __init__(self, meter: CostMeter) -> None:
        # cost_meter mirrors the real Agent's attribute — monitor.run() reads it to
        # meter the per-turn euro delta.
        self.cost_meter = meter
        self.last: str | None = None

    def run(self, text: str) -> str:
        self.last = text
        self.cost_meter.record_llm("stub", 0.01)
        return f"echo: {text}"


class _BoomAgent:
    """Raises on run() to exercise the worker error path."""

    last = None  # never set; asserts the slash path doesn't call it either

    def __init__(self, meter: CostMeter) -> None:
        self.cost_meter = meter  # monitor.run reads it before invoking run()

    def run(self, text: str) -> str:
        raise RuntimeError("kaboom")


class _ToolAgent:
    """Emits a tool-call + tool-result via the on_event observer before replying,
    standing in for the real Agent's per-dispatch events (T63). The app assigns
    `on_event`; the long result content lets the truncation be asserted."""

    LONG = "x" * 500  # longer than the TUI's truncation cap

    def __init__(self, meter: CostMeter) -> None:
        self.cost_meter = meter
        self.on_event = None  # the app overwrites this with its callback

    def run(self, text: str) -> str:
        if self.on_event is not None:
            self.on_event(
                {"type": "tool_call", "name": "read_paper", "input": {"path": "papers/x.pdf"}}
            )
            self.on_event(
                {"type": "tool_result", "name": "read_paper", "content": self.LONG, "is_error": False}
            )
        self.cost_meter.record_llm("stub", 0.01)
        return "final reply"


def test_app_smoke_reply_path(tmp_path):
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "hello"
            await pilot.press("enter")
            await app.workers.wait_for_complete()  # let the thread worker finish
            await pilot.pause()  # let the call_from_thread callback settle

            assert agent.last == "hello"  # agent was actually invoked
            prompt = app.query_one("#prompt", PromptArea)
            assert prompt.disabled is False  # re-enabled after reply
            log_text = _text(app)
            assert "hello" in log_text  # user line rendered
            assert "echo: hello" in log_text  # agent reply rendered
            # cost meter incremented (card requirement) — bar reflects the €0.01 bill
            assert "0.01" in str(app.query_one("#status", Static).render())

    asyncio.run(_drive())


def test_tui_records_per_turn_cost(tmp_path):
    """The TUI routes the turn through the monitor so each turn's euro delta is
    recorded (previously the TUI called agent.run directly and logged no turn cost)."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "hello"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

    asyncio.run(_drive())

    assert app.monitor.runs, "no per-turn cost recorded"
    assert app.monitor.runs[-1]["prompt"] == "hello"
    assert app.monitor.runs[-1]["cost_eur"] == 0.01  # _StubAgent bills €0.01


def test_agent_error_surfaces_and_reenables_input(tmp_path):
    """A raising agent.run() surfaces as an `[error]` line (from monitor.run), not a
    crash; input recovers and the monitor records the failed turn."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_BoomAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "hi"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.query_one("#prompt", PromptArea).disabled is False
            log_text = _text(app)
            assert "error" in log_text and "kaboom" in log_text
            # the TUI path records the failed turn through the monitor
            assert app.monitor.runs[-1]["ok"] is False
            assert any(i["kind"] == "exception" for i in app.monitor.issues)

    asyncio.run(_drive())


def test_tool_trace_streams_before_reply(tmp_path):
    """T63: tool calls + results stream into the log live, before the final reply,
    and long results are truncated."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _ToolAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "read the paper"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            lines = [t for _role, t in app.transcript]
            log_text = "\n".join(lines)
            # tool-call line rendered
            assert "→ read_paper" in log_text
            assert "papers/x.pdf" in log_text
            # the tool-call line appears BEFORE the final reply line (ordering)
            call_idx = next(i for i, t in enumerate(lines) if "→ read_paper" in t)
            reply_idx = next(i for i, t in enumerate(lines) if "final reply" in t)
            assert call_idx < reply_idx
            # long result truncated: ellipsis present, full 500-char blob absent
            assert "…" in log_text
            assert _ToolAgent.LONG not in log_text

    asyncio.run(_drive())


def test_tool_error_result_renders_failure_marker(tmp_path):
    """T63: a tool_result with is_error=True renders the ✗ marker, not ←."""
    meter = CostMeter(str(tmp_path / "t.db"))

    class _ErrAgent:
        def __init__(self, m):
            self.cost_meter = m
            self.on_event = None

        def run(self, text):
            if self.on_event is not None:
                self.on_event(
                    {"type": "tool_result", "name": "bash", "content": "error: nope", "is_error": True}
                )
            self.cost_meter.record_llm("stub", 0.01)
            return "done"

    app = PalimpsestApp(agent=_ErrAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "do it"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            log_text = _text(app)
            assert "✗" in log_text
            assert "error: nope" in log_text

    asyncio.run(_drive())


def test_escape_requests_cancellation_when_in_flight(tmp_path):
    """T65: the app shares one cancel event with the agent; Esc sets it only while a
    turn is in flight (input disabled), so an idle Esc can't poison the next run."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            # the agent checks the very event the app sets (one shared Event)
            assert app.agent.cancel_event is app.cancel_event

            # nothing in flight (input enabled) → Esc is a no-op
            await pilot.press("escape")
            assert app.cancel_event.is_set() is False

            # simulate a turn in flight, then Esc requests cancellation
            app.query_one("#prompt", PromptArea).disabled = True
            await pilot.press("escape")
            assert app.cancel_event.is_set() is True
            log_text = _text(app)
            assert "cancel" in log_text.lower()

    asyncio.run(_drive())


def test_streamed_reply_renders_once_via_deltas(tmp_path):
    """A1: assistant_delta events stream the reply into a live widget; the final
    reply is sealed to the transcript exactly once (not re-mounted).

    The agent's returned text deliberately differs from the concatenated deltas by a
    trailing newline (as a real provider can) — the sealed streamed text must win and
    the divergent resp.text must NOT mount a second copy (the B1 double-render bug)."""
    meter = CostMeter(str(tmp_path / "t.db"))

    class _StreamAgent:
        def __init__(self, m):
            self.cost_meter = m
            self.on_event = None

        def run(self, text):
            for d in ["Hel", "lo ", "world"]:
                if self.on_event is not None:
                    self.on_event({"type": "assistant_delta", "text": d})
            self.cost_meter.record_llm("stub", 0.01)
            return "Hello world\n"  # diverges from "Hello world" by a trailing newline

    app = PalimpsestApp(agent=_StreamAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "hi"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            agent_lines = [t for role, t in app.transcript if role == "agent"]
            assert agent_lines == ["Hello world"]  # sealed once, not doubled

    asyncio.run(_drive())


def test_clear_log_resets_stream_state(tmp_path):
    """B2: clearing the log mid-stream drops the live widget reference so the next
    delta starts fresh instead of updating a detached widget."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:  # noqa: F841 — pilot mounts the #log widget
            app._stream_append("partial reply")
            assert app._stream_widget is not None
            app.action_clear_log()
            assert app._stream_widget is None
            assert app._stream_buf == ""

    asyncio.run(_drive())


def test_streaming_render_is_throttled(tmp_path, monkeypatch):
    """A1 perf: Markdown.update re-parses the whole buffer, so it must NOT fire per
    delta (that O(n²) churn froze the UI). The buffer still accumulates every delta and
    the seal flush renders the tail — nothing is dropped."""
    from palimpsest.tui import app as appmod

    calls = {"n": 0}
    orig_update = appmod.Markdown.update

    def _counting_update(self, *a, **k):
        calls["n"] += 1
        return orig_update(self, *a, **k)

    monkeypatch.setattr(appmod.Markdown, "update", _counting_update)

    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)
    deltas = [f"tok{i} " for i in range(500)]

    async def _drive() -> None:
        async with app.run_test():  # mounts #log
            for d in deltas:
                app._stream_append(d)
            assert app._stream_widget is not None
            app._seal_stream()

    asyncio.run(_drive())

    # 500 deltas coalesce to a small handful of renders (first + ~10 Hz + final flush),
    # never one-per-delta.
    assert calls["n"] < 50, f"expected throttled renders, got {calls['n']}"
    agent_lines = [t for role, t in app.transcript if role == "agent"]
    assert agent_lines == ["".join(deltas)]  # full text preserved, nothing lost


def test_tool_pair_renders_one_collapsible(tmp_path):
    """C: a tool_call + its tool_result render as exactly ONE Collapsible whose title
    carries the summary and whose body carries the full content (expand on demand)."""
    from textual.widgets import Collapsible

    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app._show_event(
                {"type": "tool_call", "name": "read_paper", "input": {"path": "papers/x.pdf"}}
            )
            app._show_event(
                {"type": "tool_result", "name": "read_paper", "content": "l1\nl2\nl3"}
            )
            await pilot.pause()  # let the collapsible's children compose/mount
            cols = list(app.query(Collapsible))
            assert len(cols) == 1  # one widget for the pair, not two loose lines
            assert app._pending_tool is None  # call/result paired and cleared
            title = str(cols[0].title)
            assert "read_paper" in title and "3 lines" in title
            assert cols[0].collapsed is True  # counts-at-a-glance, detail on expand
            bodies = [str(s.render()) for s in cols[0].query(Static)]
            assert any("l2" in b for b in bodies)  # full content available in the body

    asyncio.run(_drive())


def test_ctrl_j_inserts_newline_without_submitting(tmp_path):
    """C1: Ctrl+J inserts a newline in the composer; Enter (not pressed here) submits."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).focus()
            await pilot.press("h", "i", "ctrl+j", "y", "o")
            assert app.query_one("#prompt", PromptArea).text == "hi\nyo"

    asyncio.run(_drive())


def test_up_arrow_recalls_input_history(tmp_path):
    """A5: a submitted line is recalled into the composer with up-arrow."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "first message"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.query_one("#prompt", PromptArea).text == ""  # cleared on submit
            await pilot.press("up")  # cursor at top-of-empty-line → history recall
            assert app.query_one("#prompt", PromptArea).text == "first message"

    asyncio.run(_drive())


def test_history_navigates_up_up_down(tmp_path):
    """A5: up walks back through MULTIPLE entries (not stuck after one), down walks
    forward, and stepping past the newest clears the line."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            for msg in ("first", "second"):
                app.query_one("#prompt", PromptArea).text = msg
                await pilot.press("enter")
                await app.workers.wait_for_complete()
                await pilot.pause()

            def text() -> str:
                return app.query_one("#prompt", PromptArea).text

            await pilot.press("up")
            assert text() == "second"
            await pilot.press("up")
            assert text() == "first"   # NOT stuck after the first up
            await pilot.press("down")
            assert text() == "second"
            await pilot.press("down")
            assert text() == ""        # past the newest → cleared

    asyncio.run(_drive())


def test_recalled_slash_command_does_not_open_menu(tmp_path):
    """Slash commands ARE kept in history; recalling one must not pop the autocomplete
    menu (which would hijack up/down and strand the user)."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            for line in ("do the thing", "/help"):
                app.query_one("#prompt", PromptArea).text = line
                await pilot.press("enter")
                await app.workers.wait_for_complete()
                await pilot.pause()

            await pilot.press("up")  # newest history entry is the slash command
            assert app.query_one("#prompt", PromptArea).text == "/help"
            assert app._menu == []   # menu suppressed while browsing — no hijack
            await pilot.press("up")  # keeps walking history, not stuck on a menu
            assert app.query_one("#prompt", PromptArea).text == "do the thing"

    asyncio.run(_drive())


def test_submit_clears_stale_cancel_before_running(tmp_path):
    """T65 race-avoidance: the app clears a stale cancel on the main thread at submit
    (before arming the in-flight guard), so a leftover Esc can't abort the new turn."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.cancel_event.set()  # stale, as if left set from before
            app.query_one("#prompt", PromptArea).text = "hello"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.cancel_event.is_set() is False  # cleared at submit
            assert agent.last == "hello"  # the run proceeded normally

    asyncio.run(_drive())


def test_slash_command_dispatched(tmp_path):
    """A `/`-prefixed line goes to the slash dispatcher, never to the agent.
    `/parser` is out of scope (T28 card), so it stays an unknown command."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "/parser docling"
            await pilot.press("enter")
            await pilot.pause()
            assert agent.last is None  # agent not called for slash commands
            log_text = _text(app)
            assert "unknown command: /parser" in log_text

    asyncio.run(_drive())


def test_slash_help_lists_commands_in_app(tmp_path):
    """`/help` renders the command list into the log (card's manual step)."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "/help"
            await pilot.press("enter")
            await pilot.pause()
            assert agent.last is None
            log_text = _text(app)
            assert "/help" in log_text and "/quit" in log_text

    asyncio.run(_drive())


def test_slash_autocomplete_shows_and_filters(tmp_path):
    """Typing `/` opens the command menu; typing more narrows it (app._menu seam)."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            menu = app.query_one("#cmdmenu", Static)
            assert menu.display is False  # hidden at rest

            app.query_one("#prompt", PromptArea).text = "/"
            await pilot.pause()
            assert menu.display is True
            for cmd in ("help", "theme", "use", "config"):
                assert cmd in app._menu
            assert "model" not in app._menu  # hidden alias of /use orchestration

            app.query_one("#prompt", PromptArea).text = "/b"
            await pilot.pause()
            assert app._menu == ["budget"]  # only /budget starts with "b"

            # a non-slash message never opens the menu
            app.query_one("#prompt", PromptArea).text = "hello"
            await pilot.pause()
            assert app.query_one("#cmdmenu", Static).display is False
            assert app._menu == []

    asyncio.run(_drive())


def test_slash_autocomplete_tab_completes(tmp_path):
    """Tab accepts the highlighted command; a no-arg command closes the menu."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "/q"  # unique prefix; /quit takes no args
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            assert app.query_one("#prompt", PromptArea).text == "/quit "
            assert app.query_one("#cmdmenu", Static).display is False

    asyncio.run(_drive())


def test_slash_autocomplete_arrow_then_enter(tmp_path):
    """Down moves the highlight; Enter on a partial value accepts that command."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "/"  # matches all, in registry order
            await pilot.pause()
            await pilot.press("down")  # help -> quit (2nd registered command)
            await pilot.pause()
            await pilot.press("enter")  # partial value "/" → accept, don't run
            await pilot.pause()
            assert app.query_one("#prompt", PromptArea).text == "/quit "
            assert app.query_one("#cmdmenu", Static).display is False

    asyncio.run(_drive())


def test_slash_autocomplete_esc_closes_menu(tmp_path):
    """Esc dismisses the menu without cancelling/clearing the input."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "/the"
            await pilot.pause()
            assert app.query_one("#cmdmenu", Static).display is True
            await pilot.press("escape")
            await pilot.pause()
            assert app.query_one("#cmdmenu", Static).display is False
            assert app.query_one("#prompt", PromptArea).text == "/the"  # input untouched

    asyncio.run(_drive())


class _ThemeStub:
    """Minimal stand-in for the app — menu_for only reads .theme (for /theme)."""

    theme = "oxide"


def test_menu_for_argument_values():
    """menu_for surfaces live registry values for the current positional arg."""
    app = _ThemeStub()

    def toks(value):
        return [t for t, _ in menu_for(app, value).rows]

    # /use is two-level: roles → providers (by role) → models under the provider.
    assert toks("/use ") == ["orchestration", "extraction", "parser"]
    # orchestration offers only loop-capable providers; extraction offers all four.
    assert toks("/use orchestration ") == ["deepseek", "anthropic"]
    assert toks("/use extraction ") == ["deepseek", "anthropic", "gemini", "openrouter"]
    # then the chosen provider's models (id + comment).
    assert toks("/use orchestration anthropic ") == ["claude-sonnet-4-6", "claude-haiku-4-5"]
    # partial filtering at the model level + the completion prefix.
    m = menu_for(app, "/use orchestration anthropic claude-h")
    assert m.rows == [("claude-haiku-4-5", "small / cheap")]
    assert m.prefix == "/use orchestration anthropic "
    # parsers come from the PARSERS registry; mineru is the marked default.
    parser_rows = dict(menu_for(app, "/use parser ").rows)
    assert set(parser_rows) == {"docling", "mineru", "chandra", "dots", "paddle"}
    assert "(default)" in parser_rows["mineru"]
    # /theme marks the active palette; /budget is a free arg (usage header, no rows).
    theme_rows = dict(menu_for(app, "/theme ").rows)
    assert "(active)" in theme_rows["oxide"]
    budget = menu_for(app, "/budget ")
    assert budget.rows == [] and budget.usage is not None
    # command mode still hides /model.
    assert "model" not in [t for t, _ in menu_for(app, "/").rows]


def test_arg_autocomplete_tab_completes(tmp_path):
    """In argument mode, Tab completes the highlighted value onto the typed line."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "/use orchestration "
            await pilot.pause()
            assert app._menu == ["deepseek", "anthropic"]  # provider level
            await pilot.press("tab")
            await pilot.pause()
            assert app.query_one("#prompt", PromptArea).text == "/use orchestration deepseek "
            # completing a provider opens the next level: that provider's models
            assert app._menu == ["deepseek-v4-flash", "deepseek-v4-pro"]
            assert app.query_one("#cmdmenu", Static).display is True

    asyncio.run(_drive())


def test_hidden_model_alias_still_dispatches(tmp_path):
    """/model is unlisted but still runs; the `anthropic` alias is still accepted."""
    meter = CostMeter(str(tmp_path / "t.db"))
    app = PalimpsestApp(agent=_StubAgent(meter), cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            for line in ("/model deepseek", "/use orchestration anthropic"):
                app.query_one("#prompt", PromptArea).text = line
                await pilot.press("enter")
                await pilot.pause()
            log = _text(app)
            assert "unknown command: /model" not in log          # hidden, not removed
            assert "can't drive the agent loop" not in log        # anthropic accepted

    asyncio.run(_drive())


def test_slash_quit_exits_the_app(tmp_path):
    """`/quit` exits the real app — and the write-after-exit("bye") doesn't crash."""
    meter = CostMeter(str(tmp_path / "t.db"))
    agent = _StubAgent(meter)
    app = PalimpsestApp(agent=agent, cost_meter=meter)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            app.query_one("#prompt", PromptArea).text = "/quit"
            await pilot.press("enter")
            await pilot.pause()
            assert agent.last is None  # agent not called
            # "bye" rendered == the write-after-exit() ran without crashing,
            # and _exit is set == app.exit() was actually invoked by the handler
            log_text = _text(app)
            assert "bye" in log_text
            assert app._exit is True

    asyncio.run(_drive())
