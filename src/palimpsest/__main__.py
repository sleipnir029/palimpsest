"""palimpsest CLI entrypoint (T08): one-shot agent run from argv.

Wires the pieces built in T04-T07 into a runnable program:
AnthropicProvider + CostMeter + Agent (with the TOOLS registry). Takes the user
message as the single command-line argument and prints the agent's answer.
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from .agent import Agent
from .cost import CostMeter
from .providers import DeepSeekProvider
from .tools import TOOLS

SYSTEM_PROMPT = (
    "You are palimpsest, an agent that extracts data from research papers. "
    "You have two tools: read_paper(path) returns a PDF's SHA-256, page count, "
    "and byte size; read_first_page_text(path) returns the text of its first "
    "page. When the user mentions a PDF path, call the tool that answers their "
    "question (use read_first_page_text for the title or authors), then answer "
    "concisely."
)


def main() -> None:
    load_dotenv()
    if len(sys.argv) < 2:
        sys.exit('usage: python -m palimpsest "<message>"')

    # T25: `demo <pdf>` runs the end-to-end pipeline and prints a summary.
    if sys.argv[1] == "demo":
        if len(sys.argv) < 3:
            sys.exit("usage: python -m palimpsest demo <pdf>")
        from pathlib import Path

        from .pipeline import run_paper  # lazy: avoid import-time coupling
        from .store import RDFStore

        # Persist to the on-disk RocksDB graph the viewer reads (RDFStore's own
        # default is in-memory, fine for tests/embedders but discarded on exit).
        # "store" matches viewer.app.STORE_PATH; RocksDB is single-writer, so run
        # this with the viewer stopped, then (re)start the viewer to read it.
        print(run_paper(Path(sys.argv[2]), store=RDFStore("store")))
        return

    agent = Agent(
        provider=DeepSeekProvider(),
        cost_meter=CostMeter("palimpsest.db"),
        # Agent advertises tool schemas to the API; it dispatches by name via the
        # module-level TOOLS registry. So pass {name: schema}, not the callables.
        tools={name: fn.tool_schema for name, fn in TOOLS.items()},
        system_prompt=SYSTEM_PROMPT,
    )
    print(agent.run(sys.argv[1]))


if __name__ == "__main__":
    main()
