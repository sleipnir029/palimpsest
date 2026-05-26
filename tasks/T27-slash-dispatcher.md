# T27 — Slash command dispatcher

## Why
Explicit control commands. Chat-first, slash-secondary per the design.

## Input state
- T26 merged. TUI works.

## Output state
- File `src/palimpsest/tui/slash.py` exports:
  - `SLASH_COMMANDS: dict[str, callable]` — initially `{"help": ..., "quit": ...}`.
  - `def dispatch(app, line: str) -> str` — parses `line` (e.g. `/budget 75`), looks up command, calls handler, returns response string for the log.
  - `/help` lists registered commands with one-line descriptions.
  - `/quit` exits the app.
  - Unknown command returns `f"unknown command: /{cmd}. type /help for available commands."`
- `tui/app.py` (edit) calls `dispatch(self, text)` when input starts with `/`.
- File `tests/test_slash.py` covers `/help`, `/quit`, unknown command paths.

## Verification
```bash
pixi run pytest tests/test_slash.py -v
pixi run tui  # type /help; verify list appears; type /quit; verify exit
```

## Will touch
- `src/palimpsest/tui/slash.py` (new)
- `src/palimpsest/tui/app.py` (edit: route slash input)
- `tests/test_slash.py` (new)

## Will NOT touch
- agent.py.

## Out of scope
- /budget, /cost, /model → T28.
- /parser, /skill, /open-viewer, /open-notebook → keep minimal in MVP; add only if needed.

## Notes / references
- Slash commands are intercepted BEFORE the agent loop. They never go to the LLM.
- Keep the dispatcher dead simple — string match, no regex magic.
