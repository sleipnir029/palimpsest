#!/usr/bin/env python
"""Scripted, monitored demo run of the palimpsest agent.

Wires the agent exactly like the CLI (``python -m palimpsest``) — load .env,
ensure the workspace repo, ensure the LLM key — then attaches a ``SessionMonitor``
to the agent's ``on_event`` hook and runs a sequence of prompts on ONE agent
instance, so context accumulates across prompts like a real session.

The monitor streams a live trace to stdout and writes
``<workspace>/.palimpsest/demo-<ts>.{log,jsonl}``; a digest of issues (tool errors,
exceptions, spend, slowest tools) prints at the end. This is the "watch the session
and find issues" half of the demo.

By default it runs a CHEAP / no-GPU script (read, list, skill, sparql, status) so a
debug iteration costs cents of DeepSeek, not a RunPod parse. Pass your own prompts
as args to override (one prompt per quoted arg):

    pixi run python scripts/demo_monitor.py
    pixi run python scripts/demo_monitor.py "what papers do I have?" "read the OER skill"

This is an ops/demo helper, NOT part of the agent itself (it uses only the public
``on_event``/``cost_meter`` surface; it never alters the loop).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a loose script (`python scripts/demo_monitor.py`) puts scripts/ on the
# path, not the repo root — but the engine imports the repo-root `schema` package
# and uses cwd-relative paths (papers/, store/, palimpsest.db). Put the repo root
# first so those resolve, the same way `python -m palimpsest` gets cwd for free.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from palimpsest.agent import build_agent
from palimpsest.config import ensure_llm_credentials, load
from palimpsest.cost import CostMeter
from palimpsest.monitor import SessionMonitor
from palimpsest.versioning import ensure_repo

# Cheap, no-GPU prompts: exercise the loop + tools (list_dir, read_paper,
# read_skill, sparql_query, workspace_status) without triggering extract_paper /
# run_paper (which spend RunPod GPU €). Each is plain language — the agent chooses
# the tools, which is exactly what we want to observe.
CHEAP_DEMO = [
    "List the PDF files in the papers/ directory.",
    "Read papers/s41467-022-35426-8.pdf and tell me the paper's title from its first page.",
    "What extraction skills are available to you? Load the oer-extraction skill and summarize what it extracts.",
    "Run a SPARQL query against the RDF graph to count how many triples are currently stored.",
    "Show me the workspace status and the current budget.",
]


def main() -> None:
    prompts = sys.argv[1:] or CHEAP_DEMO

    load()
    ensure_repo()
    ensure_llm_credentials()

    cost_meter = CostMeter("palimpsest.db")
    agent = build_agent(cost_meter=cost_meter)
    monitor = SessionMonitor()
    agent.on_event = monitor.observe

    print(f"# monitored demo · {len(prompts)} prompt(s) · log: {monitor.log_path}\n")
    for prompt in prompts:
        reply = monitor.run(agent, prompt)
        print(f"\npalimpsest> {reply}\n")

    print("\n" + monitor.summary())


if __name__ == "__main__":
    main()
