"""T08 end-to-end smoke. Makes a real Anthropic call (~€0.001-0.01); slow.

Run explicitly with `-m slow`; the offline suite uses `-m "not slow"`. Proves
the full slice works: the agent calls read_paper, answers, and the paid call
lands on the budget ledger.
"""

import os

import pytest
from dotenv import load_dotenv

from palimpsest.agent import Agent
from palimpsest.cost import CostMeter
from palimpsest.providers import AnthropicProvider
from palimpsest.tools import TOOLS

load_dotenv()

_skip_no_key = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set (.env missing or empty)",
)


@pytest.mark.slow
@_skip_no_key
def test_title_query_spends_budget(tmp_path):
    meter = CostMeter(str(tmp_path / "e2e.db"))
    agent = Agent(
        provider=AnthropicProvider(),
        cost_meter=meter,
        tools={name: fn.tool_schema for name, fn in TOOLS.items()},
        system_prompt=(
            "You are palimpsest. Tools: read_paper(path) for a PDF's "
            "SHA-256/page count/size, read_first_page_text(path) for its first "
            "page text. When the user mentions a PDF path, call the tool that "
            "answers their question, then answer concisely."
        ),
    )

    answer = agent.run("what is the title of tests/fixtures/sample.pdf?")

    assert isinstance(answer, str) and answer.strip()
    # The title contains "iridium"; surfaced via read_first_page_text. Token
    # check proves the agent actually read the paper, not just emitted prose.
    assert "iridium" in answer.lower()
    assert meter.total_eur() > 0
