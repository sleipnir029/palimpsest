"""T04 tests. These call the real Anthropic API and cost a few cents.

Cost is logged (printed) per call: Anthropic has no per-request cost endpoint,
so we compute it locally from the usage block. Persistent tracking is T05.
"""

import os

import pytest
from dotenv import load_dotenv

from palimpsest.providers import AnthropicProvider

load_dotenv()

# USD per token (card pricing for claude sonnet).
_PRICE = {
    "input_tokens": 3.00 / 1_000_000,
    "output_tokens": 15.00 / 1_000_000,
    "cache_read_input_tokens": 0.30 / 1_000_000,
    "cache_creation_input_tokens": 3.75 / 1_000_000,
}


def _estimate_cost_usd(usage: dict) -> float:
    return sum(usage.get(k, 0) * rate for k, rate in _PRICE.items())


def _log(label: str, usage: dict) -> None:
    print(f"\n[{label}] usage={usage} cost=${_estimate_cost_usd(usage):.6f}")


_skip_no_key = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set (.env missing or empty)",
)


@_skip_no_key
def test_smoke():
    provider = AnthropicProvider()
    response = provider.complete(
        system="You are helpful.",
        messages=[{"role": "user", "content": "Reply with exactly: ok"}],
    )
    _log("smoke", response.usage)
    assert response.text.strip() == "ok"


@_skip_no_key
def test_cache_control():
    provider = AnthropicProvider()
    # Cache minimum is 1024 tokens; pad well past it with repeated filler.
    system = (
        "You are a meticulous assistant. " * 400
    )  # ~2400 tokens of stable prefix
    messages = [{"role": "user", "content": "Reply with exactly: ok"}]

    first = provider.complete(
        system=system, messages=messages, cache_breakpoints=["system"]
    )
    _log("cache first", first.usage)

    second = provider.complete(
        system=system, messages=messages, cache_breakpoints=["system"]
    )
    _log("cache second", second.usage)

    print(f"\ncache_read_input_tokens={second.usage['cache_read_input_tokens']}")
    assert second.usage["cache_read_input_tokens"] > 0
