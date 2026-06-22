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


@pytest.mark.live
@_skip_no_key
def test_smoke():
    provider = AnthropicProvider()
    response = provider.complete(
        system="You are helpful.",
        messages=[{"role": "user", "content": "Reply with exactly: ok"}],
    )
    _log("smoke", response.usage)
    assert response.text.strip() == "ok"


@pytest.mark.live
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


# --- streaming path (A1), offline: stub the SDK client so no network/key needed ---


class _Block:
    def __init__(self, type_: str, text: str | None = None, dump: dict | None = None) -> None:
        self.type = type_
        if text is not None:
            self.text = text
        self._dump = dump or {}

    def model_dump(self) -> dict:
        return self._dump


class _Usage:
    input_tokens = 11
    output_tokens = 7
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _FinalMessage:
    """Mimics the anthropic Message that stream.get_final_message() returns."""

    content = [
        _Block("text", text="hello world"),
        _Block("tool_use", dump={"id": "t1", "name": "search", "input": {"q": "x"}}),
    ]
    usage = _Usage()

    def model_dump(self) -> dict:
        return {"content": [{"type": "text", "text": "hello world"}]}


class _Stream:
    def __init__(self, deltas, final) -> None:
        self.text_stream = iter(deltas)
        self._final = final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._final


class _Messages:
    def __init__(self, stream) -> None:
        self._stream = stream

    def stream(self, **kwargs):
        return self._stream

    def create(self, **kwargs):
        raise AssertionError("streaming path must not fall back to create()")


class _Client:
    def __init__(self, messages) -> None:
        self.messages = messages


def test_streaming_emits_deltas_and_assembles_same_shape():
    """on_text receives the text deltas live, and complete() still returns the SAME
    LLMResponse the loop needs (text, tool_calls, usage) from get_final_message()."""
    provider = AnthropicProvider(api_key="x")  # no network in __init__
    provider.client = _Client(_Messages(_Stream(["hello ", "world"], _FinalMessage())))

    deltas: list[str] = []
    resp = provider.complete(
        system="s",
        messages=[{"role": "user", "content": "hi"}],
        on_text=deltas.append,
    )

    assert deltas == ["hello ", "world"]              # streamed live to the UI
    assert resp.text == "hello world"                 # assembled from final message
    assert resp.tool_calls == [{"id": "t1", "name": "search", "input": {"q": "x"}}]
    assert resp.usage["input_tokens"] == 11           # usage mapped, not lost


def test_streaming_cancel_propagates_without_fallback():
    """#3: when on_text raises StreamCancelled (Esc mid-reply), complete() re-raises it
    instead of falling back to messages.create() — which would defeat the cancel."""
    from palimpsest.providers.anthropic import StreamCancelled

    provider = AnthropicProvider(api_key="x")
    # _Messages.create() asserts if reached → proves no fallback happened.
    provider.client = _Client(_Messages(_Stream(["a", "b"], _FinalMessage())))

    def on_text(_delta):
        raise StreamCancelled()

    with pytest.raises(StreamCancelled):
        provider.complete(
            system="s",
            messages=[{"role": "user", "content": "hi"}],
            on_text=on_text,
        )
