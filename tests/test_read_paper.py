"""T07 tests. Both offline — no API calls, no cost.

Test A: the read_paper tool reports correct identity/size for a real PDF.
Test B: the carried-over validation fix — a tool call missing a required arg
        comes back as a clean is_error result, not a raw TypeError.
"""

from pathlib import Path

from palimpsest.agent import Agent
from palimpsest.tools.read_paper import read_paper

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


def test_read_paper_fields():
    result = read_paper(str(FIXTURE))
    assert set(result) == {"sha256", "page_count", "bytes_len", "path"}
    assert len(result["sha256"]) == 64
    assert result["page_count"] > 0
    assert result["bytes_len"] > 1000
    assert result["path"] == str(FIXTURE)


def test_dispatch_rejects_missing_required_arg():
    # provider/cost_meter unused by _dispatch, so None is fine here.
    agent = Agent(provider=None, cost_meter=None)
    block = agent._dispatch({"id": "x", "name": "read_paper", "input": {}})
    assert block["is_error"] is True
    assert "invalid arguments" in block["content"]
    assert "TypeError" not in block["content"]  # took the clean path, not the fall-through
