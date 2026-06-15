"""DeepSeek via its Anthropic-compatible endpoint (T50).

DeepSeek serves an Anthropic-wire-format API at ``https://api.deepseek.com/anthropic``,
so we reuse the ``anthropic`` SDK and *all* of ``AnthropicProvider.complete()``'s
plumbing — we only repoint ``base_url`` and the model. Per the DeepSeek docs the
endpoint fully supports tool use (so the agent loop works unchanged) and silently
*ignores* ``cache_control`` (so ``extract``'s cache breakpoints are harmless no-ops,
not errors). No new dependency.
"""

from __future__ import annotations

import os

from .anthropic import AnthropicProvider

# USD per token, deepseek-v4-flash (api-docs.deepseek.com). Flash bills cache-hit
# and cache-miss input at the same rate, so the cache_* tiers reuse the input rate.
_DEEPSEEK_PRICE_USD = {
    "input_tokens": 0.14 / 1_000_000,
    "output_tokens": 0.28 / 1_000_000,
    "cache_read_input_tokens": 0.14 / 1_000_000,
    "cache_creation_input_tokens": 0.14 / 1_000_000,
}


class DeepSeekProvider(AnthropicProvider):
    name = "deepseek-v4-flash"
    prices = _DEEPSEEK_PRICE_USD  # read by agent/extract cost accounting
    # Disable extended thinking: deepseek-v4-flash turns it on by default, which
    # spends a large, RUN-VARIABLE share of the output budget on reasoning tokens
    # (so the JSON answer gets truncated unpredictably) and costs ~10x more output.
    # Structured extraction + simple tool calls don't need it. Verified the
    # /anthropic endpoint honors this param (returns text-only, no thinking block).
    #
    # temperature=0: reduce sampling variance (extraction feeds a thesis metric).
    # At the default 1.0 yield swung wildly run-to-run; temp=0 removes the wild swing
    # but is NOT fully deterministic — DeepSeek (MoE) still varies modestly at temp=0
    # (observed flash extraction yield ranged ~16-20 across runs). Endpoint honors
    # temperature (probe-confirmed).
    extra_request = {"thinking": {"type": "disabled"}, "temperature": 0}

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-v4-flash",
        max_tokens: int = 8192,
    ) -> None:
        # Larger default than Anthropic's 4096: the T49 extraction prompt asks for
        # verbatim source_text quotes + nested conditions per item, so a full-paper
        # extraction (10-15 measurements) overruns 4096 and truncates the JSON.
        super().__init__(
            api_key=api_key or os.environ.get("DEEPSEEK_API_KEY"),
            model=model,
            base_url="https://api.deepseek.com/anthropic",
            max_tokens=max_tokens,
        )
