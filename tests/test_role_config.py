"""App phase: three-role model config (orchestration / extraction / parser).

Selections persist in the palimpsest.db ``settings`` table (same db as the ledger);
``build_agent`` and ``extract`` resolve their provider from it. Offline — a tmp db,
no network: providers are monkeypatched to sentinels so nothing is constructed live.
"""

from __future__ import annotations

import pytest

from palimpsest import config
from palimpsest.providers import (
    ORCHESTRATION_PROVIDERS,
    PROVIDER_FACTORIES,
    AnthropicProvider,
    DeepSeekProvider,
    build_provider,
)


# --- settings round-trip ---------------------------------------------------
def test_setting_round_trip(tmp_path):
    db = str(tmp_path / "s.db")
    assert config.get_setting("extraction_model", "deepseek", db_path=db) == "deepseek"
    config.set_setting("extraction_model", "gemini", db_path=db)
    assert config.get_setting("extraction_model", db_path=db) == "gemini"


def test_setting_unset_returns_default(tmp_path):
    assert config.get_setting("nope", "fallback", db_path=str(tmp_path / "s.db")) == "fallback"


# --- provider registry -----------------------------------------------------
def test_build_provider_known():
    assert isinstance(build_provider("deepseek"), DeepSeekProvider)
    assert isinstance(build_provider("anthropic"), AnthropicProvider)


def test_build_provider_unknown_raises():
    with pytest.raises(ValueError, match="unknown provider"):
        build_provider("not-a-model")


def test_all_extraction_providers_are_priced():
    # The budget guard refuses a price-less provider, so every provider selectable for
    # extraction must carry a price table — sonnet/anthropic were relying on the
    # implicit Sonnet fallback (None on the instance), and gemini had none.
    for name in ("deepseek", "sonnet", "anthropic", "gemini"):
        prices = build_provider(name).prices
        assert prices and "input_tokens" in prices and "output_tokens" in prices, name


def test_anthropic_prices_mirror_agent_fallback():
    # AnthropicProvider.prices duplicates agent._PRICE_USD (the Sonnet fallback table
    # the €50 cap depends on). Lock the mirror so the two can't silently drift.
    from palimpsest.agent import _PRICE_USD
    from palimpsest.providers import AnthropicProvider

    assert AnthropicProvider().prices == _PRICE_USD


def test_gemini_price_is_conservative():
    # Priced at the current TOP Flash tier so a runtime extraction never UNDER-counts
    # the cap whichever Flash the drifting alias resolves to (>= the cheap 2.5 tier).
    from palimpsest.providers import GeminiProvider

    assert GeminiProvider().prices["output_tokens"] >= 2.50 / 1_000_000


def test_gemini_is_extraction_only():
    # Usable for extraction, but excluded from the agent loop (Anthropic-wire only).
    assert "gemini" in PROVIDER_FACTORIES
    assert "gemini" not in ORCHESTRATION_PROVIDERS


# --- build_agent honors orchestration_model --------------------------------
def test_build_agent_uses_orchestration_setting(tmp_path, monkeypatch):
    from palimpsest import agent as agent_mod
    from palimpsest.cost import CostMeter

    meter = CostMeter(str(tmp_path / "a.db"))
    config.set_setting("orchestration_model", "sonnet", db_path=meter.db_path)
    seen = {}
    sentinel = object()

    def fake_build(name):
        seen["name"] = name
        return sentinel

    monkeypatch.setattr("palimpsest.providers.build_provider", fake_build)
    a = agent_mod.build_agent(cost_meter=meter)
    assert seen["name"] == "sonnet"
    assert a.provider is sentinel


def test_build_agent_guards_invalid_orchestration(tmp_path, monkeypatch):
    # A non-loop provider (gemini) persisted as orchestration must fall back to the
    # default — a bad setting can never brick startup or smuggle in a non-loop model.
    from palimpsest import agent as agent_mod
    from palimpsest.cost import CostMeter

    meter = CostMeter(str(tmp_path / "a.db"))
    config.set_setting("orchestration_model", "gemini", db_path=meter.db_path)
    seen = {}

    def fake_build(name):
        seen["name"] = name
        return object()

    monkeypatch.setattr("palimpsest.providers.build_provider", fake_build)
    agent_mod.build_agent(cost_meter=meter)
    assert seen["name"] == "deepseek"


# --- extract resolves the extraction_model ---------------------------------
def test_extract_resolves_extraction_provider(tmp_path, monkeypatch):
    from palimpsest.tools import extract as ex

    db = str(tmp_path / "e.db")
    config.set_setting("extraction_model", "gemini", db_path=db)
    ex._PROVIDER_CACHE.clear()
    monkeypatch.setattr("palimpsest.providers.build_provider", lambda name: ("provider", name))
    assert ex._resolve_extraction_provider(db) == ("provider", "gemini")


def test_metered_extraction_refuses_priceless_resolved_provider(tmp_path, monkeypatch):
    """Budget guard (B1): when the extraction provider is resolved FROM CONFIG and has
    no price table (e.g. GeminiProvider, prices=None), a metered run must refuse — else
    agent._cost_eur silently charges it at Sonnet rates against the €50 cap. An injected
    provider is exempt (caller's responsibility); this drives the resolved path."""
    from palimpsest.cost import CostMeter
    from palimpsest.tools import extract as ex

    class _NoPriceProvider:
        name = "gemini-flash-latest"
        prices = None

        def complete(self, *a, **k):  # must never be reached — guard fires first
            raise AssertionError("paid call made before the price-table guard")

    meter = CostMeter(str(tmp_path / "m.db"))
    config.set_setting("extraction_model", "gemini", db_path=meter.db_path)
    ex._PROVIDER_CACHE.clear()
    monkeypatch.setattr("palimpsest.providers.build_provider", lambda name: _NoPriceProvider())

    sha = "deadbeef" * 8  # never read — the guard fires before any cache/file work
    with pytest.raises(ValueError, match="no .*price table"):
        ex.extract(paper_sha=sha, cost_meter=meter)
    assert meter.total_eur() == 0.0  # nothing charged
