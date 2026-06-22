"""llm providers."""

import os

from .anthropic import AnthropicProvider, LLMResponse
from .deepseek import DeepSeekProvider
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatProvider


def _gemini():
    """Gemini for EXTRACTION; model from GEMINI_MODEL (set by /use extraction gemini
    <model>), else the GeminiProvider default. Pricing is the conservative top-Flash
    ceiling whichever Flash is chosen, so the €-cap is never under-counted."""
    model = os.environ.get("GEMINI_MODEL")
    return GeminiProvider(model=model) if model else GeminiProvider()


def _openrouter():
    """OpenRouter (OpenAI-compatible) for EXTRACTION ONLY (user-authorized carve-out,
    CLAUDE.md 2026-06-22). NOT in ORCHESTRATION_PROVIDERS — OpenAI-compat can't drive
    the agent loop. Model from OPENROUTER_MODEL; pricing from OPENROUTER_PRICE_IN/OUT
    (USD per 1M tokens) when set, else None → _cost_eur falls back to the Sonnet table,
    a conservative ceiling so the €-cap is never UNDER-counted for a cheaper model."""
    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    prices = None
    pin, pout = os.environ.get("OPENROUTER_PRICE_IN"), os.environ.get("OPENROUTER_PRICE_OUT")
    if pin and pout:
        prices = {"input_tokens": float(pin) / 1_000_000, "output_tokens": float(pout) / 1_000_000}
    return OpenAICompatProvider(
        model=model,
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        name=model,
        prices=prices,
    )

def _priced(provider, input_usd: float, output_usd: float, *, cache_read=None, cache_create=None):
    """Attach a verified per-token USD price table to a provider INSTANCE.

    The €-budget gate (agent._cost_eur) reads provider.prices, so a non-default model
    must carry its own table or it would be mis-costed through the class default —
    under-counting the €50 cap. Prices are USD per 1M tokens (from the verified
    experiments/llm_matrix.py specs). Cache tiers default to the input rate (DeepSeek
    bills cache at input); Anthropic's 0.1x/1.25x tiers are passed explicitly.
    """
    provider.prices = {
        "input_tokens": input_usd / 1_000_000,
        "output_tokens": output_usd / 1_000_000,
        "cache_read_input_tokens": (cache_read if cache_read is not None else input_usd) / 1_000_000,
        "cache_creation_input_tokens": (cache_create if cache_create is not None else input_usd) / 1_000_000,
    }
    return provider


def _deepseek_pro():
    # deepseek-v4-pro: $0.435/$0.87 (verified, experiments/llm_matrix.py). Anthropic-wire
    # like flash, so it can drive the agent loop. DeepSeek bills cache at the input rate.
    p = DeepSeekProvider(model="deepseek-v4-pro")
    p.name = "deepseek-v4-pro"
    return _priced(p, 0.435, 0.87)


def _haiku():
    # claude-haiku-4-5: $1/$5 (verified). Anthropic cache tiers: 0.1x read, 1.25x create.
    return _priced(
        AnthropicProvider(model="claude-haiku-4-5", name="claude-haiku-4-5"),
        1.0, 5.0, cache_read=0.10, cache_create=1.25,
    )


# Short name → no-arg factory. The one registry build_agent / extract / the /use
# command all resolve through, so a model name means the same thing everywhere.
PROVIDER_FACTORIES = {
    "deepseek": DeepSeekProvider,        # deepseek-v4-flash (cheap default)
    "deepseek-pro": _deepseek_pro,       # deepseek-v4-pro (within-provider big)
    "sonnet": AnthropicProvider,         # claude-sonnet-4-6
    "haiku": _haiku,                     # claude-haiku-4-5 (small/cheap Anthropic)
    "anthropic": AnthropicProvider,
    "gemini": _gemini,                   # reads GEMINI_MODEL (extraction only)
    "openrouter": _openrouter,           # OpenAI-compat gateway, EXTRACTION ONLY
}

# Providers that can drive the AGENT LOOP. Only Anthropic-wire endpoints
# (DeepSeek/Anthropic) support tool use; Gemini/OpenAI are OpenAI-compat →
# extraction-only (openai_compat raises on tools=). T-app: orchestration stays here.
ORCHESTRATION_PROVIDERS = ("deepseek", "deepseek-pro", "sonnet", "haiku", "anthropic")


def build_provider(name: str):
    """Construct a provider by short name. Raises ValueError on an unknown name."""
    try:
        return PROVIDER_FACTORIES[name]()
    except KeyError:
        opts = ", ".join(PROVIDER_FACTORIES)
        raise ValueError(f"unknown provider: {name!r}. options: {opts}") from None


__all__ = [
    "AnthropicProvider",
    "DeepSeekProvider",
    "GeminiProvider",
    "LLMResponse",
    "OpenAICompatProvider",
    "PROVIDER_FACTORIES",
    "ORCHESTRATION_PROVIDERS",
    "build_provider",
]
