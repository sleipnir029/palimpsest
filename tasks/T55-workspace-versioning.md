# T55 — Workspace versioning (dulwich)

**Status:** ✓ done (commit `f410b9d`, 2026-06-18). Retroactive card. Fills the empty
`versioning.py` stub.

## Why
"Human supervises and verifies" only works if everything the agent does is auditable and undoable.
This is also the audit/undo net behind `bash` — originally the sole mitigation for the unfenced shell
(T54), and still the net when the OS sandbox is opted out (T85): in-workspace actions become fully
reversible.

## What was built
- `src/palimpsest/versioning.py`:
  - `ensure_repo(root)` — init a git repo in the workspace + write a `.gitignore` that excludes
    secrets/bulk state (`.env`, `config.txt`, `*.key`, `*.db`, `store/`, `cache/`). Appends the
    secret lines to a pre-existing `.gitignore` too (so an older workspace can't leak).
  - `checkpoint(message)` — `git add -A` + commit after a mutating action (no-op if nothing changed);
    `git add` via `porcelain.add` captures adds/modifications/deletions.
  - `tag_turn()` — lightweight tag at HEAD per agent turn; skips when HEAD hasn't moved.
- Hooks: `Agent._dispatch` calls `checkpoint` after each successful tool (per-action commits);
  `Agent.run` calls `tag_turn` at each turn boundary. Best-effort — a versioning hiccup never breaks
  a turn, and it no-ops off-workspace (so the test suite is side-effect-free).
- `ensure_repo()` wired into both entrypoints at startup.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_versioning.py -q   # 9 passed
# real-git probe: write_file→edit_file produced two commits + a turn tag, readable by `git log`
```

## Touched
- `src/palimpsest/versioning.py` (replace stub), `agent.py` (`_checkpoint`/`_tag_turn` hooks)
- `__main__.py` + `tui/app.py` (`ensure_repo()` at startup), `tests/test_versioning.py` (new)

## Out of scope / deferred
- Out-of-workspace `bash` writes are NOT git-tracked (the residual escape hatch — by design).
- A `/undo` agent/slash command (human uses `git revert` for now).

## Notes
- dulwich 1.2.4 dropped `Repo.stage`/`do_commit`; uses `porcelain.add` + `porcelain.commit`
  (probe-confirmed `porcelain.add(repo)` stages deletions and respects `.gitignore`).
