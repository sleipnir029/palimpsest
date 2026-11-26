"""Self-hosted / institute models: an Anthropic- or OpenAI-compatible endpoint you run.

No network: providers are only constructed, never called.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from palimpsest.providers import (
    ORCHESTRATION_PROVIDERS,
    AnthropicProvider,
    OpenAICompatProvider,
    build_provider,
)


@pytest.fixture
def local_env(monkeypatch):
    for k in ("LOCAL_PRICE_IN", "LOCAL_PRICE_OUT", "LOCAL_ANTHROPIC_API_KEY", "LOCAL_OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LOCAL_ANTHROPIC_BASE_URL", "http://gpu-node:8000")
    monkeypatch.setenv("LOCAL_ANTHROPIC_MODEL", "qwen3-32b")
    monkeypatch.setenv("LOCAL_OPENAI_BASE_URL", "http://gpu-node:8001/v1")
    monkeypatch.setenv("LOCAL_OPENAI_MODEL", "llama-3.3-70b")


def test_local_anthropic_points_at_your_server_and_can_drive_the_loop(local_env):
    p = build_provider("local-anthropic")
    assert isinstance(p, AnthropicProvider)
    assert p.model == "qwen3-32b" and p.name == "qwen3-32b"
    assert str(p.client.base_url).startswith("http://gpu-node:8000")
    assert "local-anthropic" in ORCHESTRATION_PROVIDERS


def test_local_openai_is_extraction_only(local_env):
    p = build_provider("local-openai")
    assert isinstance(p, OpenAICompatProvider)
    assert p.base_url == "http://gpu-node:8001/v1" and p.model == "llama-3.3-70b"
    assert "local-openai" not in ORCHESTRATION_PROVIDERS


def test_local_prices_default_to_conservative_sonnet_rates(local_env):
    # Unknown cost → never under-count the €-cap: meter at Sonnet rates unless told.
    for name in ("local-anthropic", "local-openai"):
        prices = build_provider(name).prices
        assert prices["input_tokens"] == pytest.approx(3.0 / 1e6)
        assert prices["output_tokens"] == pytest.approx(15.0 / 1e6)


def test_local_prices_from_env_allow_free_inference(local_env, monkeypatch):
    monkeypatch.setenv("LOCAL_PRICE_IN", "0")
    monkeypatch.setenv("LOCAL_PRICE_OUT", "0")
    for name in ("local-anthropic", "local-openai"):
        assert build_provider(name).prices["output_tokens"] == 0.0


def test_local_requires_url_and_model(monkeypatch):
    monkeypatch.delenv("LOCAL_ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_ANTHROPIC_MODEL", raising=False)
    with pytest.raises(ValueError, match="LOCAL_ANTHROPIC_BASE_URL"):
        build_provider("local-anthropic")


def test_use_orchestration_local_sets_model_and_switches(local_env, monkeypatch, tmp_path):
    from palimpsest import config
    from palimpsest.tui import slash

    monkeypatch.setattr(config, "_env_path", lambda: tmp_path / ".env")
    app = SimpleNamespace(agent=SimpleNamespace(provider=None),
                          cost_meter=SimpleNamespace(db_path=str(tmp_path / "p.db")))
    out = slash._use(app, ["orchestration", "local-anthropic", "my-model"])
    assert "my-model" in out
    assert app.agent.provider.model == "my-model"
    assert config.get_setting("orchestration_model", db_path=str(tmp_path / "p.db")) == "local-anthropic"


def test_use_extraction_local_openai(local_env, monkeypatch, tmp_path):
    from palimpsest import config
    from palimpsest.tui import slash

    monkeypatch.setattr(config, "_env_path", lambda: tmp_path / ".env")
    app = SimpleNamespace(agent=SimpleNamespace(provider=None),
                          cost_meter=SimpleNamespace(db_path=str(tmp_path / "p.db")))
    slash._use(app, ["extraction", "local-openai", "mistral-small"])
    assert config.get_setting("extraction_model", db_path=str(tmp_path / "p.db")) == "local-openai"
    assert build_provider("local-openai").model == "mistral-small"


def test_cached_tokens_are_never_free(local_env):
    """The Anthropic wire reports cache reads/creations separately from input_tokens;
    they must be priced (at least at the input rate), or the €-cap under-counts."""
    from palimpsest.agent import _cost_eur

    usage = {"input_tokens": 100, "output_tokens": 0,
             "cache_read_input_tokens": 100_000, "cache_creation_input_tokens": 50_000}
    sonnet = _cost_eur(usage, build_provider("sonnet").prices)
    local = _cost_eur(usage, build_provider("local-anthropic").prices)
    assert local >= sonnet  # input-rate cache pricing over-counts, never under-counts


def test_negative_price_rejected(local_env, monkeypatch):
    monkeypatch.setenv("LOCAL_PRICE_IN", "-1")
    monkeypatch.setenv("LOCAL_PRICE_OUT", "0")
    with pytest.raises(ValueError, match=">= 0"):
        build_provider("local-openai")


def test_anthropic_key_not_forwarded_to_your_server(local_env, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real")
    assert build_provider("local-anthropic").client.api_key == "none"


def test_startup_survives_unconfigured_local_model(monkeypatch, tmp_path, capsys):
    from palimpsest import config
    from palimpsest.agent import build_agent
    from palimpsest.cost import CostMeter

    monkeypatch.setenv("LOCAL_ANTHROPIC_BASE_URL", "http://gpu-node:8000")
    monkeypatch.delenv("LOCAL_ANTHROPIC_MODEL", raising=False)
    db = str(tmp_path / "p.db")
    config.set_setting("orchestration_model", "local-anthropic", db_path=db)
    agent = build_agent(cost_meter=CostMeter(db))
    assert agent.provider.name.startswith("deepseek")
    assert "LOCAL_ANTHROPIC_MODEL" in capsys.readouterr().out


def test_use_extraction_model_change_takes_effect(local_env, monkeypatch, tmp_path):
    from palimpsest import config
    from palimpsest.tools.extract import _resolve_extraction_provider
    from palimpsest.tui import slash

    monkeypatch.setattr(config, "_env_path", lambda: tmp_path / ".env")
    db = str(tmp_path / "p.db")
    app = SimpleNamespace(agent=SimpleNamespace(provider=None),
                          cost_meter=SimpleNamespace(db_path=db))
    slash._use(app, ["extraction", "local-openai", "first"])
    assert _resolve_extraction_provider(db).model == "first"
    slash._use(app, ["extraction", "local-openai", "second"])
    assert _resolve_extraction_provider(db).model == "second"


def test_placeholder_model_is_rejected(local_env, monkeypatch, tmp_path):
    from palimpsest import config
    from palimpsest.tui import slash

    monkeypatch.setattr(config, "_env_path", lambda: tmp_path / ".env")
    app = SimpleNamespace(agent=SimpleNamespace(provider=None),
                          cost_meter=SimpleNamespace(db_path=str(tmp_path / "p.db")))
    out = slash._use(app, ["orchestration", "local-anthropic", "<model>"])
    assert "give the model name" in out
    assert not (tmp_path / ".env").exists()
