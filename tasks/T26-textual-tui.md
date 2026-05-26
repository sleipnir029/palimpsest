# T26 — Textual chat skeleton

## Why
The user-facing TUI: chat-first interface where Rahat types natural language and the agent does the work.

## Input state
- T25 merged. The pipeline works end-to-end.

## Output state
- File `src/palimpsest/tui/app.py` exports:
  - Class `PalimpsestApp(textual.App)`:
    - Layout: top bar with cost meter (`€spent / €cap`), main scrollable message log, bottom input box.
    - `on_input_submitted` → if starts with `/`, dispatch to slash handler (stub for T27); else, call `agent.run(text)` and append response to log.
    - Cost meter updates after each agent.run() by reading from CostMeter.
    - Bindings: `ctrl+q` quit, `ctrl+l` clear log.
  - Module entry: `def main()` constructs Agent, AnthropicProvider, CostMeter, ParserCache, RDFStore, SkillLoader, registers tools, runs the app.
- `pixi.toml` adds task `tui = "python -m palimpsest.tui"`.
- File `src/palimpsest/tui/__main__.py` calls `app.main()`.
- File `src/palimpsest/tui/styles.tcss` (optional) for layout polish.
- File `tests/test_tui.py` smoke-tests that `PalimpsestApp` can instantiate without errors (use Textual's pilot API or just `App.run_test()`).

## Verification
```bash
pixi run tui            # opens TUI; quit with Ctrl+Q
pixi run pytest tests/test_tui.py -v
```
TUI opens cleanly. Typing "hello" produces an agent reply. Cost meter increments.

## Will touch
- `src/palimpsest/tui/app.py` (full)
- `src/palimpsest/tui/__main__.py` (new)
- `src/palimpsest/tui/styles.tcss` (optional new)
- `pixi.toml` (edit: add tui task)
- `tests/test_tui.py` (new)

## Will NOT touch
- src/palimpsest/agent.py (T06 stable).
- src/palimpsest/tools/* (stable).

## Out of scope
- Slash command dispatcher → T27.
- /budget /cost /model implementations → T28.
- Viewer integration → T29-T31.

## Notes / references
- Textual docs: https://textual.textualize.io/
- Keep this MVP. One screen, one input box, one log, one status bar. Don't add tabs, sidebars, or other widgets.
- If `agent.run()` is slow, run it in a worker thread so the UI stays responsive. Textual has `@work` decorator for this.
