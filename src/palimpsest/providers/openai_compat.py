"""OpenAI-compatible chat-completions adapter (T72) — extraction only.

`httpx`-only, no new SDK (httpx is already pinned). Drives any OpenAI
``/chat/completions`` endpoint — OpenAI itself, Qwen (DashScope/Together),
Gemini's OpenAI-compat endpoint (see ``gemini.py``), or a local Ollama/vLLM/
llama.cpp server — so the T72 breadth matrix can benchmark *extractors* across
model tiers without touching the agent loop.

EXTRACTION ONLY: ``complete(tools=...)`` raises. The agent loop is locked to the
Anthropic wire format (it reads Anthropic ``content``/``usage`` and threads
tool-calls back); driving it with this adapter would need per-provider tool-call
translation, which T72 explicitly excludes. ``extract.py`` already calls
``provider.complete(..., tools=None)`` and parses ``resp.text`` as JSON, so this
adapter is all that's needed for the benchmark.

Pricing is NOT baked here: ``prices`` (USD/token, the table ``_cost_eur`` reads)
is supplied by the caller after verifying the provider's rates at run time.
"""

from __future__ import annotations

import os

import httpx

from .anthropic import LLMResponse


class OpenAICompatProvider:
    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str | None = None,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        name: str | None = None,
        prices: dict | None = None,
        # 16384 (not 8192): reasoning models spend hidden thinking tokens against
        # max_tokens, truncating the JSON at a lower ceiling. 16384 gives room while
        # staying within most models' output caps (some, e.g. qwen3-235b, cap at 16384;
        # requesting above a model's cap can 400). Gemini overrides this higher.
        # It's only a cap — non-thinking models stop early, costing nothing extra.
        max_tokens: int = 16384,
        temperature: float = 0.0,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.name = name or model
        # USD/token {input_tokens, output_tokens}; read via getattr by _cost_eur.
        # Left None for providers whose rates aren't verified — the matrix records
        # tokens and leaves cost blank rather than baking a guess.
        self.prices = prices
        self.max_tokens = max_tokens
        self.temperature = temperature  # 0 for reproducible extraction metrics
        self._key = api_key or os.environ.get(api_key_env)
        # `client` is the test-injection seam (httpx.MockTransport); real runs build
        # their own.
        self._client = client or httpx.Client(timeout=timeout)

    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        cache_breakpoints: list[str] | None = None,
    ) -> LLMResponse:
        if tools is not None:
            raise NotImplementedError(
                "OpenAICompatProvider is extraction-only (tools must be None); it does "
                "not drive the agent loop — see the T72 card / CLAUDE.md."
            )
        # cache_breakpoints accepted-and-ignored: OpenAI endpoints have no explicit
        # cache-control field (mirrors how DeepSeek's endpoint ignores cache_control).
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        headers = {"Authorization": f"Bearer {self._key}"}
        resp = self._client.post(
            f"{self.base_url}/chat/completions", json=payload, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"].get("content") or ""
        u = data.get("usage") or {}
        usage = {
            "input_tokens": u.get("prompt_tokens", 0),
            "output_tokens": u.get("completion_tokens", 0),
        }
        return LLMResponse(text=text, tool_calls=[], usage=usage, raw=data)
