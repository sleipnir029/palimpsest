"""llm providers."""

from .anthropic import AnthropicProvider, LLMResponse
from .deepseek import DeepSeekProvider
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatProvider

# Short name → no-arg factory. The one registry build_agent / extract / the /use
# command all resolve through, so a model name means the same thing everywhere.
PROVIDER_FACTORIES = {
    "deepseek": DeepSeekProvider,
    "sonnet": AnthropicProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}

# Providers that can drive the AGENT LOOP. Only Anthropic-wire endpoints
# (DeepSeek/Anthropic) support tool use; Gemini/OpenAI are OpenAI-compat →
# extraction-only (openai_compat raises on tools=). T-app: orchestration stays here.
ORCHESTRATION_PROVIDERS = ("deepseek", "sonnet", "anthropic")


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
