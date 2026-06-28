# T85 — OS-sandbox the bash escape hatch

**Status:** ✓ done (2026-06-28). Reverses T54's "bash stays unsandboxed" deferral.

## Why
`bash` was cwd-pinned but NOT filesystem-fenced (T54): a shell could `rm`/overwrite
anything the OS user could reach — engine code, `$HOME`, the OS. An autonomous run
could veer off and destroy files outside the workspace. The structured write tools
were already code-confined; the escape hatch was the remaining hole. This makes the
hatch's filesystem boundary OS-enforced too — strengthening, not weakening, the
constrained-autonomy thesis.

## What was built
- `src/palimpsest/sandbox.py`:
  - `mechanism()` — `"seatbelt"` (macOS `sandbox-exec`), `"bwrap"` (Linux), else `None`.
  - `seatbelt_profile(root)` — `allow default` (reads/exec/network) → `deny file-write*`
    → re-allow writes under the workspace + system temp (`tempfile.gettempdir()`,
    `/private/tmp`, `/private/var/tmp`) + `/dev` std fds → re-deny `store/`, `cache/`,
    `*.db`, `*.key`, secret names (Seatbelt is last-match-wins). Protected paths reuse
    `policy._PROTECTED_*` (single source).
  - `wrap(command, root)` — `sandbox-exec -p PROFILE /bin/bash -c …` (or a best-effort,
    **unverified** bwrap argv), or raises `PolicyViolation` if no mechanism.
- `src/palimpsest/tools/bash.py` — default-on, **fail-closed**: sandbox required unless
  `config bash_sandbox=off`; no mechanism → refuse. Runs via `Popen` in a new session and
  SIGKILLs the whole process group on timeout (no orphaned grandchildren). Still not a
  spend gate.
- `policy.py` — added `_PROTECTED_SUFFIXES=(".db",".key")` (single source for both
  `assert_writable` and the sandbox).

## Boundary (user-chosen)
- Writes/deletes confined to the workspace (+ system temp scratch). **Reads and network
  stay open** — this stops file/OS destruction, not exfiltration.
- `store/`, `cache/`, `*.db`, `*.key`, `.env` denied to bash too, matching `write_file`.
- Fail-closed default-on; `/config set bash_sandbox off` = the raw, unfenced hatch.

## Verification
```bash
pixi run pytest tests/test_sandbox.py tests/test_policy.py -q   # all pass; seatbelt cases run on macOS
```
Empirically validated: write inside ok; write/rm/symlink-target outside blocked; nested
`sandbox-exec` can't widen the fence; reads + `mktemp` + `/dev/null` work; `store/`/`*.db`/
`.env` denied even in the allowed temp tree; `sleep 30` @ `timeout=1` leaves no orphan.

## Touched
- `src/palimpsest/sandbox.py` (new), `tools/bash.py`, `policy.py`
- `tests/test_sandbox.py` (new), `tests/test_policy.py`
- docs: `CLAUDE.md`, `policy.py`/`bash.py` docstrings, `tasks/T54`

## Known limits
- Reads + network open by design (not an exfiltration fence).
- `sandbox-exec` is Apple-deprecated (still shipped/functional, used by Chromium/Claude Code).
- Linux `bwrap` path is best-effort and **unverified** on the macOS dev box; its `*.db`/`*.key`/
  `.env` suffix denies are Seatbelt-only (bwrap binds are path-based) — verify before Linux deploy.
- Global `*.db` deny means the agent can't create a scratch sqlite db anywhere (matches `write_file`).
