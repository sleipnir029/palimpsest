# T## — <short kebab-case name>

## Why
One sentence on why this task exists. What does it unlock?

## Input state
- T<prev> is merged.
- The repo has <existing files/state>.
- <Anything else that must be true>.

## Output state
- File `<path>` exists and exports `<symbol>` with signature `<sig>`.
- `<some behavior>` works when invoked as `<command>`.
- One test at `tests/<path>` covers the happy path.

## Verification
```
pixi run pytest tests/<file> -v
# OR a specific one-liner
pixi run python -c "<one-liner that prints success>"
```
The verification command MUST exit 0 and produce specific output for the task to be done.

## Will touch
- `src/palimpsest/<file>` (new)
- `src/palimpsest/<other>` (edit: <what change>)
- `tests/<file>` (new)

## Will NOT touch
- `CLAUDE.md`, `EXECUTION.md`, `palimpsest-v2-design.md`
- `pixi.toml` (unless explicitly listed)
- Any file in `<dir>` (unless explicitly listed)
- `PROGRESS.md` (only updated at merge time by `merge` step)

## Out of scope
- <related-thing-1> → T## later
- <related-thing-2> → T## later

## Notes / references
- Pattern reference: <link or section of palimpsest-v2-design.md>
- Key library docs: <links>
- Pitfalls to avoid: <one-liner>
