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


def _cost_eur(usage: dict, prices: dict | None = None) -> float:
    # `prices` is the provider's USD/token table (DeepSeekProvider.prices etc.);
    # defaults to the Sonnet table so callers/stubs without one keep working.
    table = prices or _PRICE_USD
    usd = sum(usage.get(key, 0) * rate for key, rate in table.items())
    return usd * _USD_TO_EUR


class Agent:
    def __init__(
        self,
        provider,
        cost_meter,
        tools: dict | None = None,
        system_prompt: str = "",
        max_turns: int = 40,
        on_event=None,
    ) -> None:
        self.provider = provider
        self.cost_meter = cost_meter
        self.tools = tools or {}
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.messages: list[dict] = []
        self.last_usage: dict = {}  # usage block of the most recent LLM call
        # Passive observer (T63): fires per tool call + result so a supervisor (the
        # TUI) can watch the loop live. Default None = no-op; never alters dispatch.
        self.on_event = on_event

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
                self.provider.name,
                _cost_eur(resp.usage, getattr(self.provider, "prices", None)),
                detail=f"turn {turn}",
            )
            # Append the assistant turn verbatim: the API needs the original
            # content blocks (text + tool_use) back to continue the conversation.
            self.messages.append({"role": "assistant", "content": resp.raw["content"]})

            if not resp.tool_calls:
                self._tag_turn()  # mark this turn's boundary in the workspace git log
                return resp.text

            results = []
            for call in resp.tool_calls:
                self._emit({"type": "tool_call", "name": call["name"], "input": call["input"]})
                result = self._dispatch(call)
                self._emit({
                    "type": "tool_result",
                    "name": call["name"],
                    # every _dispatch path returns a dict with "content"; .get just
                    # avoids a KeyError if a future branch omits the key.
                    "content": result.get("content", ""),
                    "is_error": result.get("is_error", False),
                })
                results.append(result)
            self.messages.append({"role": "user", "content": results})

        raise MaxTurnsExceeded(f"no final answer in {self.max_turns} turns")

    def _emit(self, event: dict) -> None:
        """Notify the passive observer of a tool event (best-effort, T63).

        A faulty observer must never alter the agent loop, so failures are
        swallowed — same contract as `_tag_turn`/`_checkpoint`.
        """
        if self.on_event is None:
            return
        try:
            self.on_event(event)
        except Exception:  # noqa: BLE001 — observation must never break a turn
            pass

    @staticmethod
    def _tag_turn() -> None:
        """Tag the workspace git HEAD at a turn boundary (best-effort, no-op off-workspace)."""
        from . import versioning

        try:
            versioning.tag_turn()
        except Exception:  # noqa: BLE001 — versioning must never break a turn
            pass

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
        else:
            self._checkpoint(call)  # per-action git commit (no-op if nothing changed)
        return block

    @staticmethod
    def _checkpoint(call: dict) -> None:
        """Commit the workspace after a successful tool call (best-effort)."""
        from . import versioning

        inp = call.get("input") or {}
        detail = inp.get("path") or inp.get("command") or inp.get("pdf_path") or ""
        try:
            versioning.checkpoint(f"{call['name']}: {detail}".strip()[:72])
        except Exception:  # noqa: BLE001 — versioning must never break a tool call
            pass


def build_system_prompt(cost_meter) -> str:
    """Compose the agent's system prompt from the live tool registry + skills.

    Built once at construction (not per turn) so it stays a stable prefix for
    prompt caching — re-rendering it every turn would bust the cache (CLAUDE.md).
    The budget line is an opening hint; the TUI cost bar shows live spend.
    """
    tool_lines = "\n".join(
        f"- {name}: {fn.tool_schema['description']}" for name, fn in sorted(TOOLS.items())
    )
    from .tools.read_skill import _LOADER  # already constructed via the tools import

    skills = _LOADER.manifest() or "(none)"
    return (
        "You are palimpsest, an autonomous research agent. You turn research PDFs "
        "into a queryable, ontology-aligned RDF knowledge graph, and you help with "
        "the surrounding code, notebooks, and analysis.\n\n"
        f"## Budget\nSpent €{cost_meter.total_eur():.2f} of €{cost_meter.cap:.0f}. "
        "Paid work (extract_paper, GPU parsing) is metered and refused at the cap; "
        "prefer cached parser output and don't re-parse needlessly.\n\n"
        f"## Tools\n{tool_lines}\n\n"
        f"## Skills\n{skills}\n"
        "Load a skill's full guidance with read_skill before extracting in its domain.\n\n"
        "## Working rules\n"
        "- You operate inside a workspace: read freely, and create/edit files (code, JSON, "
        "markdown, notebooks, schema, ontology) there.\n"
        "- write_file and edit_file are confined to the workspace by the system — they refuse "
        "the engine and its fixtures. bash is more powerful and is NOT fenced: keep its work "
        "inside the workspace, and never use it to touch the engine, the graph store, or the ledger.\n"
        "- Populate the RDF graph ONLY via extract_paper (it attaches provenance) and let spend "
        "be metered; never hand-edit the graph store or the cost ledger.\n"
        "- If a tool reports missing config (e.g. an API key), ask the user to provide it via "
        "/config — never invent, guess, or fabricate secrets or values.\n"
        "- The human supervises and verifies (viewer + git), so say what you did."
    )


def build_agent(provider=None, cost_meter=None) -> "Agent":
    """Construct the standard palimpsest agent (one place, used by CLI + TUI).

    Replaces the copy-pasted ``{name: fn.tool_schema}`` + static prompt that had
    drifted between ``__main__.py`` and ``tui/app.py``. Defaults to DeepSeek + the
    on-disk ledger; both are injectable for tests.
    """
    from .cost import CostMeter
    from .providers import DeepSeekProvider

    cost_meter = cost_meter if cost_meter is not None else CostMeter("palimpsest.db")
    provider = provider if provider is not None else DeepSeekProvider()
    return Agent(
        provider=provider,
        cost_meter=cost_meter,
        tools={name: fn.tool_schema for name, fn in TOOLS.items()},
        system_prompt=build_system_prompt(cost_meter),
    )
