"""T06 tests. These call the real Anthropic API and cost a few cents.

Each test uses a throwaway SQLite ledger (tmp_path) so the budget starts fresh.
"""

import os

import pytest
from dotenv import load_dotenv

from palimpsest.agent import Agent, MaxTurnsExceeded
from palimpsest.cost import CostMeter
from palimpsest.providers import AnthropicProvider
from palimpsest.providers.anthropic import LLMResponse
from palimpsest.tools import register

load_dotenv()

_skip_no_key = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set (.env missing or empty)",
)


# A tool that always raises, used to drive the loop to max_turns.
@register("always_fails", {
    "description": "Always raises an error. Call this to attempt the task.",
    "input_schema": {"type": "object", "properties": {}},
})
def always_fails() -> str:
    raise RuntimeError("boom")


@_skip_no_key
def test_no_tools(tmp_path):
    meter = CostMeter(str(tmp_path / "c.db"))
    agent = Agent(AnthropicProvider(), meter, tools={})
    out = agent.run("Reply with exactly 'pong' and nothing else.")
    assert out.strip() == "pong"

    n_llm = meter.conn.execute(
        "SELECT COUNT(*) FROM cost_ledger WHERE kind = 'llm'"
    ).fetchone()[0]
    assert n_llm == 1


@_skip_no_key
def test_cache_hit_on_second_run(tmp_path):
    meter = CostMeter(str(tmp_path / "c.db"))
    # Cache minimum is 1024 tokens; pad the stable system prefix well past it.
    system = "You are a meticulous extraction agent. " * 400  # ~2800 tokens
    agent = Agent(AnthropicProvider(), meter, tools={}, system_prompt=system)

    agent.run("Reply with exactly 'one'.")
    agent.run("Reply with exactly 'two'.")

    cache_read = agent.last_usage["cache_read_input_tokens"]
    print(f"\ncache_read = {cache_read}")
    assert cache_read > 0


class _AlwaysCallsToolProvider:
    """Stub provider: every turn emits a tool_call, so the loop never finishes.

    The max_turns bound is pure control flow, so this is tested deterministically
    (and for free) rather than hoping the live model keeps calling a failing tool.
    """

    name = "stub"

    def complete(self, system, messages, tools, cache_breakpoints):
        call = {"id": "t1", "name": "always_fails", "input": {}}
        return LLMResponse(
            text="",
            tool_calls=[call],
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            raw={"content": [{"type": "tool_use", **call}]},
        )


def test_max_turns(tmp_path):
    meter = CostMeter(str(tmp_path / "c.db"))
    agent = Agent(
        _AlwaysCallsToolProvider(),
        meter,
        tools={"always_fails": always_fails.tool_schema},
        max_turns=3,
    )
    with pytest.raises(MaxTurnsExceeded):
        agent.run("Do the task.")
