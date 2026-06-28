# T54 — Constrained-autonomy policy + guarded write/edit/bash

**Status:** ✓ done (commit `8dd1801`, 2026-06-18). Retroactive card. This is the thesis core:
*how to give an autonomous agent write access without it violating the invariants that make the
output trustworthy* — enforced in code, not suggested in a prompt.

## Why
The agent needs to write, edit, and run things, but must not corrupt the engine, the provenance
graph, the budget ledger, or secrets. The enforced boundary is the contribution.

## What was built
- `src/palimpsest/policy.py`:
  - `workspace_root()` — `$PALIMPSEST_WORKSPACE`, default `./workspace` (dev sandbox).
  - `assert_writable(path)` — confine to the workspace via `resolve()`+`relative_to` (defeats `..`,
    symlinks, and the `workspace`-vs-`workspace-evil` prefix-collision); refuse the graph `store/`,
    parser `cache/`, the ledger (`*.db`), and secrets (`config.txt`, `.env`, `*.key`).
  - `assert_bash_allowed(cmd)` — best-effort foot-gun guard against un-metered spend (whitespace-
    normalized), NOT a security boundary.
- `tools/write_file.py`, `tools/edit_file.py` (exact unique-match replace) — confined via the policy.
- `tools/bash.py` — cwd-pinned to the workspace; a **supervised escape hatch**, deliberately NOT
  filesystem-fenced (the Claude Code model).

## Decision + review log
- Decision (user): bash stays unsandboxed; its filesystem/spend integrity relies on the human + git
  (the dulwich audit/undo net of T55), not an OS sandbox.
- Independent review returned **FAIL** — the prompt/docstrings overstated bash as code-confined.
  Fixed: every claim scoped to what the code enforces (write_file/edit_file confined; bash is the
  escape hatch), and `test_bash_is_not_filesystem_confined` makes that an explicit, tested fact.
  Re-review cleared the residual docstring overstatement.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_policy.py -q   # 16 passed
```

## Touched
- `src/palimpsest/policy.py` (new), `tools/{write_file,edit_file,bash}.py` (new)
- `tests/test_policy.py` (new), `.gitignore` (ignore `workspace/`)

## Out of scope / deferred
- ~~OS-sandboxing bash (would make its fs boundary code-enforced) — deferred; git checkpointing covers
  the realistic risk.~~ **Done in T85** — bash is now OS-sandboxed (writes workspace-confined) by
  default, fail-closed. The `test_bash_is_not_filesystem_confined` fact from this card is inverted
  there (`test_bash_writes_are_confined_to_workspace`); the unconfined behavior survives only behind
  the explicit `bash_sandbox=off` opt-out.
- Per-workspace vs global graph/cache/ledger paths — portability phase.
