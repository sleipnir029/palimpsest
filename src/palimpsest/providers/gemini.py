"""Gemini via its OpenAI-compatible endpoint (T72) — extraction only.

Google serves an OpenAI ``/chat/completions``-shaped API at
``https://generativelanguage.googleapis.com/v1beta/openai``. We reuse
``OpenAICompatProvider`` over that base_url rather than add the ``google-genai``
SDK: httpx already covers it with zero new dependency. (CLAUDE.md lists the Gemini
SDK as an *allowed* fallback, but the locked stack favours not adding a dep we
don't need.)

The model id and pricing are NOT baked: pass them in after verifying Gemini's
current tiers/rates at run time (T72), the same as for OpenAI/Qwen.
"""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

# `gemini-flash-latest` is a drifting alias — it tracks Google's newest Flash, whose
# price varies by tier (Gemini 2.5 Flash $0.30/$2.50, Gemini 3.5 Flash $1.50/$9.00 per
# MTok — ai.google.dev/gemini-api/docs/pricing, 2026-06). We bake the CURRENT TOP Flash
# tier so a runtime extraction is metered *conservatively*: the €50 cap is never
# UNDER-counted whichever Flash the alias resolves to. Experiments pass an exact
# model+prices and override this; the default only powers `/use extraction gemini`.
_GEMINI_PRICE_USD = {
    "input_tokens": 1.50 / 1_000_000,
    "output_tokens": 9.00 / 1_000_000,
}


class GeminiProvider(OpenAICompatProvider):
    def __init__(
        self,
        model: str = "gemini-flash-latest",
        api_key: str | None = None,
        *,
        name: str | None = None,
        prices: dict | None = None,
        max_tokens: int = 32768,
        **kwargs,
    ) -> None:
        prices = prices if prices is not None else _GEMINI_PRICE_USD
        # Gemini 3.x Flash is a thinking model: it spends a large, variable share of the
        # token budget on hidden reasoning, so the JSON answer truncates at the base
        # 16384 ceiling. Give it more headroom (its output cap is 64K+).
        super().__init__(
            model=model,
            base_url=_GEMINI_BASE_URL,
            api_key=api_key,
            api_key_env="GEMINI_API_KEY",
            name=name or model,
            prices=prices,
            max_tokens=max_tokens,
            **kwargs,
        )
