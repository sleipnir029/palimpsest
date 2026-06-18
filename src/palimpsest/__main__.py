"""palimpsest CLI entrypoint (T08): one-shot agent run from argv.

Wires the pieces built in T04-T07 into a runnable program:
AnthropicProvider + CostMeter + Agent (with the TOOLS registry). Takes the user
message as the single command-line argument and prints the agent's answer.
"""

from __future__ import annotations

import sys

from .agent import build_agent
from .config import ensure_llm_credentials, load


def main() -> None:
    load()
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

    # Init the workspace git repo so the agent's actions are logged + undoable.
    from .versioning import ensure_repo

    ensure_repo()
    ensure_llm_credentials()  # prompt + save the provider key if missing (never invent)
    # One factory builds the agent (tools + dynamic system prompt) for CLI and TUI.
    print(build_agent().run(sys.argv[1]))


if __name__ == "__main__":
    main()
