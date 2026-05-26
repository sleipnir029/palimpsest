"""T08 tests for the read_first_page_text tool. Offline — no API calls, no cost.

The tool extracts a PDF's first-page text so the agent can answer title/author
questions that read_paper (metadata only) can't.
"""

from pathlib import Path

from palimpsest.tools.read_first_page_text import read_first_page_text

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


def test_read_first_page_text_returns_title():
    text = read_first_page_text(str(FIXTURE))
    assert isinstance(text, str) and text.strip()
    # The fixture's title contains "Iridium"; its presence proves real first-page
    # text came back, not an empty or wrong page.
    assert "iridium" in text.lower()
