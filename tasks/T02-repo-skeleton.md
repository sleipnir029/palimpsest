# T02 — repo skeleton

## Why
Pre-create every directory the project will need so subsequent tasks have a defined home for new files. This prevents Claude from inventing alternative layouts mid-project.

## Input state
- T01 merged. `pixi install` works. `pixi run python -c "import palimpsest"` returns `ok`.
- Top-level directories exist (created at project bootstrap): `tasks/`, `papers/`, `src/palimpsest/`, `schema/`, `skills/`, `docker/`, `notebooks/`, `tests/`, `queries/`, `experiments/`, `thesis/`.
- `src/palimpsest/__init__.py` exists.

## Output state
The following subdirectories and `__init__.py` files exist under `src/palimpsest/`:

```
src/palimpsest/
├── __init__.py            (already from T01)
├── agent.py               (empty stub: '"""agent loop."""')
├── cost.py                (empty stub)
├── cache.py               (empty stub)
├── store.py               (empty stub)
├── validation.py          (empty stub)
├── ontology.py            (empty stub)
├── versioning.py          (empty stub)
├── providers/
│   └── __init__.py
├── parsers/
│   └── __init__.py
├── tools/
│   └── __init__.py
├── tui/
│   └── __init__.py
└── viewer/
    ├── __init__.py
    ├── templates/         (empty)
    └── static/            (empty)
```

Also create:
- `tests/__init__.py` (empty)
- `tests/fixtures/.gitkeep` (empty file)
- `papers/.gitkeep` (empty file)
- `schema/generated/.gitkeep`
- `cache/.gitkeep` (note: `cache/` itself is gitignored from T01, but `.gitkeep` allows the directory to exist)

Each "empty stub" .py file contains a single line: `"""<module purpose>."""`.

## Verification
```bash
pixi run python -c "
import palimpsest
import palimpsest.agent
import palimpsest.cost
import palimpsest.cache
import palimpsest.store
import palimpsest.validation
import palimpsest.ontology
import palimpsest.versioning
import palimpsest.providers
import palimpsest.parsers
import palimpsest.tools
import palimpsest.tui
import palimpsest.viewer
print('all imports ok')
"
```
Must exit 0 and print `all imports ok`.

## Will touch
- All files listed under Output state.

## Will NOT touch
- `pixi.toml`, `pixi.lock`, `pyproject.toml`, `.gitignore`
- `CLAUDE.md`, `EXECUTION.md`, `palimpsest-v2-design.md`, `README.md`, `SETUP.md`, `PROGRESS.md`, `DEVIATIONS.md`
- Any file in `tasks/`

## Out of scope
- Implementing anything in the stubs — they are just placeholders.
- Adding subdirectory structures beyond what's listed above.
- Writing any test logic — just the `__init__.py` and `.gitkeep` markers.

## Notes / references
- Layout matches Appendix B of `palimpsest-v2-design.md` exactly.
- `.gitkeep` is a convention; the file itself is empty and exists only to let git track the directory.
- Resist the temptation to add docstrings beyond one line — the stubs are placeholders, not documentation.
