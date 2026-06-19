"""T72 — OpenAI-compatible extraction adapter.

Offline: a stubbed HTTP transport feeds a canned /chat/completions response and we
assert the adapter (a) maps text + token usage into an `LLMResponse`, (b) sends the
system prompt + caller messages in OpenAI shape, and (c) REFUSES `tools` — it is an
extraction-only completion adapter, never an agent driver (the agent loop is locked
to the Anthropic wire; see the T72 card / CLAUDE.md).
"""

from __future__ import annotations

import httpx
import pytest

from palimpsest.providers import GeminiProvider, LLMResponse, OpenAICompatProvider


def _client(handler) -> httpx.Client:
    """An httpx.Client whose requests are served by `handler` — no real network."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_response(captured: dict):
    """A handler that records the outgoing request and returns a canned completion."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "model": "stub-model",
                "choices": [{"message": {"role": "assistant", "content": "hello world"}}],
                "usage": {"prompt_tokens": 1234, "completion_tokens": 56},
            },
        )

    return handler


def test_complete_maps_text_and_usage():
    p = OpenAICompatProvider(
        model="m", base_url="https://x/v1", api_key="k", client=_client(_ok_response({}))
    )
    resp = p.complete(system="sys", messages=[{"role": "user", "content": "hi"}], tools=None)

    assert isinstance(resp, LLMResponse)
    assert resp.text == "hello world"
    assert resp.tool_calls == []
    # OpenAI's prompt/completion tokens map onto the Anthropic-shaped usage keys that
    # `_cost_eur` reads.
    assert resp.usage["input_tokens"] == 1234
    assert resp.usage["output_tokens"] == 56


def test_complete_sends_system_then_user_messages():
    captured: dict = {}
    p = OpenAICompatProvider(
        model="mymodel", base_url="https://x/v1", api_key="secret",
        client=_client(_ok_response(captured)),
    )
    p.complete(system="SYSTEM", messages=[{"role": "user", "content": "USER"}])

    req = captured["request"]
    assert req.url.path.endswith("/chat/completions")
    assert req.headers["authorization"] == "Bearer secret"
    import json
    body = json.loads(req.content)
    assert body["model"] == "mymodel"
    assert body["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert body["messages"][1] == {"role": "user", "content": "USER"}


def test_complete_raises_on_tools():
    p = OpenAICompatProvider(
        model="m", base_url="https://x/v1", api_key="k", client=_client(_ok_response({}))
    )
    with pytest.raises(NotImplementedError):
        p.complete(system="s", messages=[{"role": "user", "content": "u"}], tools=[{"name": "t"}])


def test_cache_breakpoints_accepted_and_ignored():
    # extract() always passes cache_breakpoints=["system"]; OpenAI endpoints have no
    # explicit cache control, so the adapter must accept the kwarg without erroring.
    p = OpenAICompatProvider(
        model="m", base_url="https://x/v1", api_key="k", client=_client(_ok_response({}))
    )
    resp = p.complete(
        system="s", messages=[{"role": "user", "content": "u"}],
        tools=None, cache_breakpoints=["system"],
    )
    assert resp.text == "hello world"


def test_complete_handles_missing_usage_block():
    # Local Ollama / some proxies omit `usage`; must default to 0/0, not KeyError.
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    p = OpenAICompatProvider(model="m", base_url="https://x/v1", api_key="k", client=_client(handler))
    resp = p.complete(system="s", messages=[{"role": "user", "content": "u"}])
    assert resp.usage == {"input_tokens": 0, "output_tokens": 0}


def test_complete_handles_null_content():
    # A tool-less refusal / empty completion can return content: null → map to "".
    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": None}}], "usage": {"prompt_tokens": 9, "completion_tokens": 0}},
        )

    p = OpenAICompatProvider(model="m", base_url="https://x/v1", api_key="k", client=_client(handler))
    resp = p.complete(system="s", messages=[{"role": "user", "content": "u"}])
    assert resp.text == ""


def test_complete_raises_on_http_error():
    # A 4xx/5xx (bad model id, dead endpoint) must surface as an error so the matrix
    # skips that model rather than recording a bogus row.
    def handler(request):
        return httpx.Response(404, json={"error": "model not found"})

    p = OpenAICompatProvider(model="bad", base_url="https://x/v1", api_key="k", client=_client(handler))
    with pytest.raises(httpx.HTTPStatusError):
        p.complete(system="s", messages=[{"role": "user", "content": "u"}])


def test_gemini_provider_uses_openai_compat_endpoint():
    captured: dict = {}
    p = GeminiProvider(model="gemini-flash-latest", api_key="g", client=_client(_ok_response(captured)))
    resp = p.complete(system="s", messages=[{"role": "user", "content": "u"}])

    assert resp.text == "hello world"
    # Routed through Google's OpenAI-compatible endpoint, not a new SDK.
    assert "generativelanguage.googleapis.com" in str(captured["request"].url)
    assert captured["request"].url.path.endswith("/chat/completions")
