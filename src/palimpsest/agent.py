"""Agent loop: think -> act -> observe, with prompt caching on system + tools.

The core of palimpsest (design F2), modeled on the Anthropic cookbook agents
pattern and Thorsten Ball's "How to Build an Agent". The message history lives on
the instance (`self.messages`); every turn is metered against the budget before
the paid call and recorded after.
"""

from __future__ import annotations

from jsonschema import ValidationError, validate

from .tools import TOOLS

# USD per token, Sonnet pricing (card T06). 5-minute cache-creation tier.
_PRICE_USD = {
    "input_tokens": 3.00 / 1_000_000,
    "output_tokens": 15.00 / 1_000_000,
    "cache_read_input_tokens": 0.30 / 1_000_000,
    "cache_creation_input_tokens": 3.75 / 1_000_000,
}
_USD_TO_EUR = 0.92


class MaxTurnsExceeded(Exception):
    pass


def _cost_eur(usage: dict) -> float:
    usd = sum(usage.get(key, 0) * rate for key, rate in _PRICE_USD.items())
    return usd * _USD_TO_EUR


class Agent:
    def __init__(
        self,
        provider,
        cost_meter,
        tools: dict | None = None,
        system_prompt: str = "",
        max_turns: int = 40,
    ) -> None:
        self.provider = provider
        self.cost_meter = cost_meter
        self.tools = tools or {}
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.messages: list[dict] = []
        self.last_usage: dict = {}  # usage block of the most recent LLM call

    def run(self, user_msg: str) -> str:
        self.messages.append({"role": "user", "content": user_msg})

        # Cache only what exists: an empty system/tools block can't be cached.
        breakpoints = [
            bp
            for bp, present in (("system", self.system_prompt), ("tools", self.tools))
            if present
        ]

        for turn in range(self.max_turns):
            self.cost_meter.check_or_raise(projected_eur=0.05)  # conservative
            resp = self.provider.complete(
                system=self.system_prompt,
                messages=self.messages,
                tools=list(self.tools.values()),
                cache_breakpoints=breakpoints,
            )
            self.last_usage = resp.usage
            self.cost_meter.record_llm(
                self.provider.name, _cost_eur(resp.usage), detail=f"turn {turn}"
            )
            # Append the assistant turn verbatim: the API needs the original
            # content blocks (text + tool_use) back to continue the conversation.
            self.messages.append({"role": "assistant", "content": resp.raw["content"]})

            if not resp.tool_calls:
                return resp.text

            results = [self._dispatch(call) for call in resp.tool_calls]
            self.messages.append({"role": "user", "content": results})

        raise MaxTurnsExceeded(f"no final answer in {self.max_turns} turns")

    def _dispatch(self, call: dict) -> dict:
        """Run one tool call, returning an Anthropic tool_result block.

        Tool errors are surfaced back to the model as `is_error` results rather
        than raised, so it can recover (or keep failing until max_turns).
        """
        block: dict = {"type": "tool_result", "tool_use_id": call["id"]}
        fn = TOOLS.get(call["name"])
        if fn is None:
            return {**block, "content": f"error: unknown tool {call['name']!r}", "is_error": True}
        try:
            validate(call["input"], fn.tool_schema["input_schema"])
        except ValidationError as exc:
            return {**block, "content": f"error: invalid arguments: {exc.message}", "is_error": True}
        try:
            block["content"] = str(fn(**call["input"]))
        except Exception as exc:  # noqa: BLE001 — surface any tool failure to the model
            block.update(content=f"error: {exc}", is_error=True)
        return block
