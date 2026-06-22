"""T28: /budget, /cost, /model handlers. Offline — a real temp CostMeter (stdlib
sqlite3, no network) + a tiny fake app carrying .cost_meter and .agent.provider.
/model construction is monkeypatched so the switch is asserted without live keys."""

from __future__ import annotations

from palimpsest.cost import CostMeter
from palimpsest.tui import slash
from palimpsest.tui.slash import dispatch


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
    out = dispatch(_app(tmp_path), "/model haiku")
    assert "not implemented" in out


def test_model_unknown(tmp_path):
    out = dispatch(_app(tmp_path), "/model bogus")
    assert "unknown model" in out


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


def test_use_orchestration_anthropic_is_valid(tmp_path, monkeypatch):
    # anthropic is a valid loop provider (same class as sonnet) and must be reachable
    # at runtime, not just at startup — the two registries are kept in sync.
    from palimpsest import config

    monkeypatch.setitem(slash._PROVIDERS, "anthropic", _DummyProvider)
    app = _app(tmp_path)
    out = dispatch(app, "/use orchestration anthropic")
    assert "switched" in out
    assert config.get_setting("orchestration_model", db_path=app.cost_meter.db_path) == "anthropic"


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
