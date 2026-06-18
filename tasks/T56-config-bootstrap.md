# T56 — Config bootstrap ("ask, don't invent")

**Status:** ✓ done (commit `517e9b4`, 2026-06-18). Retroactive card.

## Why
Spawned in a fresh directory, a missing API key crashed the agent mid-chat with a cryptic SDK auth
error (or a raw `KeyError` for RunPod). The agent must **ask the user** for missing config and never
fabricate secrets/values — the Claude-Code first-run-setup pattern.

## What was built
- `src/palimpsest/config.py`:
  - `load(workspace)` — load the workspace `.env` first (wins for the spawn model), then cwd `.env`
    (dev convenience; never overrides).
  - `ensure_llm_credentials(provider, prompt=getpass)` — if the active provider's key is missing,
    prompt (hidden) and save to the workspace `.env`; warn (don't silently proceed) if left blank.
  - `set_value(key, value)` — write/update the workspace `.env` + `os.environ` (prefix-collision safe).
- Startup check wired into both entrypoints (terminal getpass before the Textual loop — no modal).
- `/config` slash command — show keys (masked) / `/config set KEY VALUE` (reloads the provider if it's
  the active key).
- Secret-leak guards: `.env` excluded from the dulwich auto-commit (T55 `.gitignore`) AND refused by
  the write policy (T54 `_PROTECTED_NAMES`).
- `extract_paper` turns a missing `RUNPOD_API_KEY` into an actionable ask; the system prompt instructs
  the agent to ask for missing config, never invent it.

## Review log
- Two review blockers fixed: (1) `ensure_repo` only wrote `.gitignore` when absent → an older
  workspace would commit `.env` (secret leak) — now appends the secret lines; (2) `extract_paper`'s
  KeyError guard mislabeled ANY KeyError as missing-RunPod when RunPod was unset — narrowed to the
  real `KeyError('RUNPOD_API_KEY')`.

## Verification
```bash
ANTHROPIC_API_KEY="" pixi run pytest tests/test_config.py -q   # 13 passed
ANTHROPIC_API_KEY="" pixi run pytest -m "not slow" -q          # 196 passed, 0 failures
```

## Touched
- `src/palimpsest/config.py` (new), `tui/slash.py` (`/config`), `agent.py` (prompt rule)
- `tools/run_paper.py` (friendly missing-RunPod), `versioning.py` (`.gitignore` += `.env`/`*.key`)
- `policy.py` (`_PROTECTED_NAMES` += `.env`; `.key` suffix), `__main__.py` + `tui/app.py` (startup
  check), `tests/test_config.py` (new), `.env.example` (+`DEEPSEEK_API_KEY`)

## Out of scope / deferred
- RunPod creds are asked on demand (only a GPU parse needs them), not at startup.
- Where config ultimately lives in deployment (user-level vs spawn folder) — portability phase.
