"""Anthropic SDK wrapper — the only LLM client used in the MVP."""

from __future__ import annotations

import os
from dataclasses import dataclass

import anthropic


class StreamCancelled(Exception):
    """Raised from on_text to abort an in-flight streamed reply (user pressed Esc).

    Distinct from a transport error so the streaming path re-raises it instead of
    falling back to a fresh blocking call (which would defeat the cancellation).
    """


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict]
    usage: dict
    raw: dict


class AnthropicProvider:
    name = "claude-sonnet-4-6"
    # USD/token, Claude Sonnet 4.6 — $3/$15 per MTok, cache-read 0.1x, cache-creation
    # 1.25x (confirmed via the claude-api reference, 2026-06). Mirrors agent._PRICE_USD
    # (kept there as the fallback for price-less test stubs). Explicit here so the
    # extraction budget guard sees a real table — DeepSeekProvider overrides it.
    prices = {
        "input_tokens": 3.00 / 1_000_000,
        "output_tokens": 15.00 / 1_000_000,
        "cache_read_input_tokens": 0.30 / 1_000_000,
        "cache_creation_input_tokens": 3.75 / 1_000_000,
    }
    # Extra request kwargs merged into every messages.create() call. Subclasses
    # override (e.g. DeepSeekProvider disables extended thinking). Anthropic's
    # default is no thinking, so the base leaves this empty.
    extra_request: dict = {}

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
        base_url: str | None = None,
        name: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        if name is not None:
            self.name = name
        client_kwargs: dict = {"api_key": api_key or os.environ.get("ANTHROPIC_API_KEY")}
        if base_url is not None:
            # Repoint the SDK at an Anthropic-wire-compatible endpoint (DeepSeek
            # serves one at /anthropic — see DeepSeekProvider).
            client_kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**client_kwargs)

    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        cache_breakpoints: list[str] | None = None,
        on_text=None,
    ) -> LLMResponse:
        breakpoints = cache_breakpoints or []

        if "system" in breakpoints:
            system_arg: object = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_arg = system

        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_arg,
            "messages": messages,
        }

        if tools is not None:
            tools = [dict(t) for t in tools]  # copy; never mutate caller's list
            if "tools" in breakpoints and tools:
                tools[-1]["cache_control"] = {"type": "ephemeral"}
            kwargs["tools"] = tools

        kwargs.update(self.extra_request)
        if on_text is None:
            # Non-streaming path (CLI + extraction): unchanged, one blocking call.
            response = self.client.messages.create(**kwargs)
        else:
            # Streaming path (the TUI agent loop): push text deltas to on_text as
            # they arrive, then assemble the SAME final Message the loop needs
            # (tool_use blocks + usage) from get_final_message().
            try:
                with self.client.messages.stream(**kwargs) as stream:
                    for delta in stream.text_stream:
                        on_text(delta)  # may raise StreamCancelled (Esc mid-reply)
                    response = stream.get_final_message()
            except StreamCancelled:
                raise  # user cancelled — do NOT fall back to a fresh blocking call
            except Exception:  # noqa: BLE001 — endpoint may not stream cleanly
                # ponytail: a stream that fails (typically on the first call, before
                # any delta) falls back to one blocking call so the turn still
                # completes — the reply just doesn't stream. A rare mid-stream
                # failure could double-render partial text; acceptable for an MVP.
                response = self.client.messages.create(**kwargs)

        # Only "text" blocks are the answer; a provider may also return "thinking"
        # blocks (extended reasoning) which we neither surface nor thread back.
        text = "".join(b.text for b in response.content if b.type == "text")
        tool_calls = [
            b.model_dump() for b in response.content if b.type == "tool_use"
        ]
        u = response.usage
        usage = {
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0)
            or 0,
        }

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            usage=usage,
            raw=response.model_dump(),
        )
