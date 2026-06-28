"""T28: /budget, /cost, /model handlers. Offline — a real temp CostMeter (stdlib
sqlite3, no network) + a tiny fake app carrying .cost_meter and .agent.provider.
/model construction is monkeypatched so the switch is asserted without live keys."""

from __future__ import annotations

import pytest

from palimpsest.cost import CostMeter
from palimpsest.tui import slash
from palimpsest.tui.slash import dispatch


@pytest.fixture(autouse=True)
def _isolate_workspace(tmp_path, monkeypatch):
    """Point the workspace at tmp so /resume's session scan never reads the real
    ./workspace (it now lists rotated session files off disk)."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))


class _FakeAgent:
    def __init__(self) -> None:
        self.provider = object()  # stand-in for the initial provider


class _FakeApp:
    def __init__(self, cost_meter: CostMeter) -> None:
        self.cost_meter = cost_meter
        self.agent = _FakeAgent()


def _app(tmp_path) -> _FakeApp:
    return _FakeApp(CostMeter(str(tmp_path / "t.db")))


# /budget -------------------------------------------------------------------
def test_budget_raises_cap(tmp_path):
    app = _app(tmp_path)
    out = dispatch(app, "/budget 75")
    assert app.cost_meter.cap == 75
    assert "75" in out and "headroom" in out


def test_budget_below_spend_refused(tmp_path):
    app = _app(tmp_path)
    app.cost_meter.record_llm("deepseek-v4-flash", 30.0, detail="seed")
    out = dispatch(app, "/budget 10")
    assert "refused" in out
    assert app.cost_meter.cap == 50  # unchanged from the seeded default


def test_budget_non_int_is_friendly(tmp_path):
    app = _app(tmp_path)
    out = dispatch(app, "/budget abc")
    assert "usage" in out
    assert app.cost_meter.cap == 50  # no crash, no change


# /cost ---------------------------------------------------------------------
def test_cost_summary(tmp_path):
    app = _app(tmp_path)
    app.cost_meter.record_llm("deepseek-v4-flash", 0.05, detail="turn 0")
    app.cost_meter.record_gpu(0.10, detail="docling pod")
    out = dispatch(app, "/cost")
    assert "0.15" in out                 # total spent
    assert "llm" in out and "gpu" in out  # breakdown by kind
    assert "docling pod" in out           # last-10 ledger tail


def test_cost_empty_ledger(tmp_path):
    # Fresh meter, no spend: total is €0, no "last entries:" header (the if-rows branch).
    out = dispatch(_app(tmp_path), "/cost")
    assert "0.0000" in out
    assert "last entries:" not in out


# /model --------------------------------------------------------------------
class _DummyProvider:
    name = "dummy-model"

    def __init__(self) -> None:
        pass


def test_model_switch_reassigns_provider(tmp_path, monkeypatch):
    # Patch the registry the handler actually reads, not the module symbol (the dict
    # captured the class refs at import), so the switch is asserted without live keys.
    monkeypatch.setitem(slash._PROVIDERS, "deepseek", _DummyProvider)
    app = _app(tmp_path)
    out = dispatch(app, "/model deepseek")
    assert isinstance(app.agent.provider, _DummyProvider)
    assert "switched" in out and "dummy-model" in out


def test_model_construction_failure_is_friendly(tmp_path, monkeypatch):
    class _Boom:
        def __init__(self) -> None:
            raise RuntimeError("no api key")

    monkeypatch.setitem(slash._PROVIDERS, "sonnet", _Boom)
    app = _app(tmp_path)
    before = app.agent.provider
    out = dispatch(app, "/model sonnet")
    assert "could not switch" in out
    assert app.agent.provider is before  # left intact on failure


def test_model_not_implemented(tmp_path):
    # gemini is extraction-only (OpenAI-compat, no tool use) → can't drive the loop.
    out = dispatch(_app(tmp_path), "/model gemini")
    assert "not implemented" in out


def test_model_unknown(tmp_path):
    out = dispatch(_app(tmp_path), "/model bogus")
    assert "unknown model" in out


def test_use_orchestration_specific_model_switches(tmp_path):
    """Two-level pick: provider then model. haiku under anthropic switches the loop
    with its own pricing (real provider built offline, no API call)."""
    app = _app(tmp_path)
    out = dispatch(app, "/use orchestration anthropic claude-haiku-4-5")
    assert "switched to claude-haiku-4-5" in out
    # the switched provider carries verified haiku pricing (not the sonnet default)
    assert round(app.agent.provider.prices["input_tokens"] * 1_000_000, 2) == 1.0


def test_model_persists_orchestration_setting(tmp_path, monkeypatch):
    from palimpsest import config

    monkeypatch.setitem(slash._PROVIDERS, "deepseek", _DummyProvider)
    app = _app(tmp_path)
    dispatch(app, "/model deepseek")
    assert config.get_setting("orchestration_model", db_path=app.cost_meter.db_path) == "deepseek"


# /use ----------------------------------------------------------------------
def test_use_orchestration_rejects_non_loop_provider(tmp_path):
    # Gemini can't drive the agent loop (OpenAI-compat → extraction-only). /use gates
    # on ORCHESTRATION_PROVIDERS and points the user at /use extraction instead.
    out = dispatch(_app(tmp_path), "/use orchestration gemini")
    assert "can't drive the agent loop" in out
    assert "extraction" in out


def test_use_orchestration_anthropic_is_valid(tmp_path):
    # anthropic is a valid loop provider; with no model it defaults to its first model
    # (sonnet), persisted as the priced factory name.
    from palimpsest import config

    app = _app(tmp_path)
    out = dispatch(app, "/use orchestration anthropic")
    assert "switched" in out
    assert config.get_setting("orchestration_model", db_path=app.cost_meter.db_path) == "sonnet"


def test_use_extraction_persists(tmp_path):
    from palimpsest import config

    app = _app(tmp_path)
    out = dispatch(app, "/use extraction gemini")
    assert "extraction" in out and "gemini" in out
    assert config.get_setting("extraction_model", db_path=app.cost_meter.db_path) == "gemini"


def test_use_extraction_unknown_provider(tmp_path):
    assert "unknown provider" in dispatch(_app(tmp_path), "/use extraction bogus")


def test_use_parser_persists_and_validates(tmp_path):
    from palimpsest import config

    app = _app(tmp_path)
    assert "parser" in dispatch(app, "/use parser docling")
    assert config.get_setting("parser_name", db_path=app.cost_meter.db_path) == "docling"
    assert "unknown parser" in dispatch(app, "/use parser bogus")


def test_use_unknown_role(tmp_path):
    assert "unknown role" in dispatch(_app(tmp_path), "/use bogus x")


def test_use_usage_on_missing_args(tmp_path):
    assert "usage" in dispatch(_app(tmp_path), "/use orchestration")


# /theme --------------------------------------------------------------------
def test_theme_switch_persists(tmp_path):
    from palimpsest import config

    app = _app(tmp_path)
    out = dispatch(app, "/theme oxide")
    assert "oxide" in out
    assert app.theme == "oxide"
    assert config.get_setting("ui_theme", db_path=app.cost_meter.db_path) == "oxide"


def test_theme_unknown(tmp_path):
    assert "unknown theme" in dispatch(_app(tmp_path), "/theme nope")


def test_theme_lists_available(tmp_path):
    out = dispatch(_app(tmp_path), "/theme")
    assert "scriptorium" in out and "vellum" in out and "catalogue" in out


# /resume -------------------------------------------------------------------
class _ResumeAgent:
    """Agent stub exposing the two attributes /resume touches: session + messages."""

    def __init__(self, msgs):
        self.provider = object()
        self.messages: list = []
        self.session = type("_S", (), {"load": lambda _self, limit=None: list(msgs)})()


def _resume_app(tmp_path, msgs):
    app = _FakeApp(CostMeter(str(tmp_path / "t.db")))
    app.agent = _ResumeAgent(msgs)
    return app


def test_resume_trim_drops_dangling_tail():
    from palimpsest.tui.slash import _resume_trim

    clean = {"role": "assistant", "content": [{"type": "text", "text": "done"}]}
    msgs = [
        {"role": "user", "content": "hi"},
        clean,
        {"role": "user", "content": "extract x"},
        {"role": "assistant", "content": [{"type": "tool_use", "name": "extract_paper", "id": "1", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "ok"}]},
    ]
    # a cancelled-mid-turn tail (tool_use + tool_result, no reply) trims back to the
    # last clean assistant answer so the restored history is API-valid.
    assert _resume_trim(msgs)[-1] is clean


def test_resume_recap_shows_text_exchanges():
    from palimpsest.tui.slash import _resume_recap

    msgs = [
        {"role": "user", "content": "hello there"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi back"}]},
    ]
    out = _resume_recap(msgs)
    assert "hello there" in out and "hi back" in out


def test_resume_restores_context(tmp_path):
    msgs = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": [{"type": "text", "text": "earlier answer"}]},
    ]
    app = _resume_app(tmp_path, msgs)
    out = dispatch(app, "/resume")
    assert "resumed 2 message" in out and "earlier question" in out
    assert app.agent.messages[-1]["content"][0]["text"] == "earlier answer"


def _write_session(session_id, msgs, mtime):
    import os

    from palimpsest.session import SessionLog

    log = SessionLog(session_id=session_id)
    for m in msgs:
        log.append(m)
    os.utime(log.current_path, (mtime, mtime))


def test_resume_picks_specific_prior_session(tmp_path):
    """#5: /resume <n> selects the nth prior session (1 = newest), excludes current,
    and bounds-checks. Uses two REAL rotated sessions (the fallback tests don't)."""
    (tmp_path / ".git").mkdir()  # open the session-log write gate (mirrors ensure_repo)
    _write_session("20260101-000000-aaaaaa",
                   [{"role": "user", "content": "old q"},
                    {"role": "assistant", "content": [{"type": "text", "text": "old a"}]}], 1000)
    _write_session("20260102-000000-bbbbbb",
                   [{"role": "user", "content": "new q"},
                    {"role": "assistant", "content": [{"type": "text", "text": "new a"}]}], 2000)
    app = _resume_app(tmp_path, [])  # stub session has no current_path → excludes nothing

    out1 = dispatch(app, "/resume 1")  # newest prior
    assert "new q" in out1 and app.agent.messages[0]["content"] == "new q"
    out2 = dispatch(app, "/resume 2")  # older
    assert "old q" in out2 and app.agent.messages[0]["content"] == "old q"
    assert "no session #9" in dispatch(app, "/resume 9")  # out of range


def test_deepseek_pro_carries_its_own_pricing(tmp_path):
    """Budget invariant: deepseek-v4-pro (under deepseek) switches with its verified
    table, not the flash/sonnet default."""
    app = _app(tmp_path)
    out = dispatch(app, "/use orchestration deepseek deepseek-v4-pro")
    assert "switched to deepseek-v4-pro" in out
    assert round(app.agent.provider.prices["input_tokens"] * 1_000_000, 3) == 0.435


def test_openrouter_is_extraction_only(tmp_path):
    """OpenRouter is selectable for extraction (CLAUDE.md carve-out) but NOT for the
    agent loop (OpenAI-compat can't drive it)."""
    from palimpsest.providers import ORCHESTRATION_PROVIDERS, PROVIDER_FACTORIES, build_provider

    assert "openrouter" in PROVIDER_FACTORIES
    assert "openrouter" not in ORCHESTRATION_PROVIDERS
    assert build_provider("openrouter").base_url.startswith("https://openrouter.ai")
    # rejected as a loop driver, accepted as an extractor
    assert "can't drive the agent loop" in dispatch(_app(tmp_path), "/use orchestration openrouter")


def test_use_extraction_openrouter_persists(tmp_path):
    from palimpsest import config

    app = _app(tmp_path)
    out = dispatch(app, "/use extraction openrouter")
    assert "openrouter" in out
    assert config.get_setting("extraction_model", db_path=str(tmp_path / "t.db")) == "openrouter"


def test_use_extraction_gateway_model_sets_env(tmp_path, monkeypatch):
    """Two-level extraction: a gateway provider carries the chosen model in an env var
    (OPENROUTER_MODEL), persisted to the workspace .env; the role setting is the provider."""
    from palimpsest import config

    monkeypatch.setenv("OPENROUTER_MODEL", "")  # register for cleanup (set_value mutates os.environ)
    app = _app(tmp_path)
    out = dispatch(app, "/use extraction openrouter deepseek/deepseek-chat")
    assert "openrouter" in out and "deepseek/deepseek-chat" in out
    assert "OPENROUTER_MODEL=deepseek/deepseek-chat" in (tmp_path / ".env").read_text()
    assert config.get_setting("extraction_model", db_path=str(tmp_path / "t.db")) == "openrouter"


def test_resume_empty_session(tmp_path):
    app = _resume_app(tmp_path, [])
    assert "no prior session" in dispatch(app, "/resume")
    assert app.agent.messages == []  # nothing clobbered when there's nothing to load


# /git + /review ------------------------------------------------------------
def test_git_shows_workspace_history(tmp_path, monkeypatch):
    """/git renders the workspace action tree from versioning.recent_history."""
    from palimpsest import versioning

    monkeypatch.setattr(versioning, "_last_tagged", None)
    monkeypatch.setattr(versioning, "_turn", 0)
    versioning.ensure_repo()  # workspace is tmp_path (autouse fixture)
    (tmp_path / "note.md").write_text("hi", encoding="utf-8")
    versioning.checkpoint("did a thing")
    versioning.tag_turn()

    out = dispatch(_app(tmp_path), "/git")
    assert "workspace history" in out
    assert "did a thing" in out
    assert "turn-" in out  # the turn tag marker is shown


def test_git_empty_when_no_repo(tmp_path):
    out = dispatch(_app(tmp_path), "/git")  # tmp workspace, never ensure_repo'd
    assert "no workspace history" in out


def test_review_command_is_registered_and_listed():
    """/review is dispatch-known (for /help + menu); the TUI runs it as an agent turn."""
    assert "review" in slash.VISIBLE_COMMANDS
    assert "review" in slash.SLASH_COMMANDS
    assert slash.REVIEW_PROMPT.strip()  # a non-empty prompt the TUI submits
