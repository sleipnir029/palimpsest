"""Anthropic SDK wrapper — the only LLM client used in the MVP."""

from __future__ import annotations

import os
from dataclasses import dataclass

import anthropic


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict]
    usage: dict
    raw: dict


class AnthropicProvider:
    name = "claude-sonnet-4-6"
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
