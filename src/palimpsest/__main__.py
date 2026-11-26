"""palimpsest CLI entrypoint (T08): one-shot agent run from argv.

Wires the pieces built in T04-T07 into a runnable program:
AnthropicProvider + CostMeter + Agent (with the TOOLS registry). Takes the user
message as the single command-line argument and prints the agent's answer.
"""

from __future__ import annotations

import sys

from .agent import build_agent
from .config import ensure_role_credentials, load


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

    # Bring-your-own-agent: a coding agent plays the extraction model (no API key).
    if sys.argv[1] in ("prompt", "ingest"):
        import argparse

        from . import external  # lazy

        ap = argparse.ArgumentParser(prog=f"python -m palimpsest {sys.argv[1]}")
        ap.add_argument("pdf")
        ap.add_argument("--parser", default="docling", choices=external.PARSERS)
        ap.add_argument("--skill", default="oer-extraction")
        if sys.argv[1] == "prompt":
            ap.add_argument("--out", help="write the prompt here instead of stdout")
            a = ap.parse_args(sys.argv[2:])
            text = external.render_prompt(a.pdf, a.parser, a.skill)
            if a.out:
                from pathlib import Path

                Path(a.out).parent.mkdir(parents=True, exist_ok=True)
                Path(a.out).write_text(text, encoding="utf-8")
                print(f"prompt written to {a.out}")
            else:
                print(text)
        else:
            ap.add_argument("--response", required=True, help="file with the JSON answer")
            a = ap.parse_args(sys.argv[2:])
            try:
                print(external.ingest(a.pdf, a.response, a.parser, a.skill))
            except OSError as exc:
                if "LOCK" not in str(exc):
                    raise
                sys.exit("the graph store is locked: stop the viewer (or other palimpsest "
                         "process) and run ingest again")
            from .tools.extraction_report import extraction_report

            print(extraction_report(a.pdf, a.parser))  # what was dropped, and why
        return

    # Init the workspace git repo so the agent's actions are logged + undoable.
    from .versioning import ensure_repo

    ensure_repo()
    ensure_role_credentials()  # prompt + save orchestration/extraction keys if missing
    # One factory builds the agent (tools + dynamic system prompt) for CLI and TUI.
    print(build_agent().run(sys.argv[1]))


if __name__ == "__main__":
    main()
