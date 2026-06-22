"""Config + secrets bootstrap — ask the user, never invent.

palimpsest is spawned in a workspace; required credentials live in the workspace
``.env`` (gitignored — see ``versioning._GITIGNORE``). On startup the entrypoints
call ``ensure_llm_credentials``, which prompts in the terminal for a missing
provider key and saves it, so the agent never crashes mid-chat with a cryptic SDK
auth error and never fabricates a secret. RunPod creds are asked on demand (only
a GPU parse needs them) — see ``tools/run_paper.py``.
"""

from __future__ import annotations

import getpass
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

from .cost import canonical_db
from .policy import workspace_root

# Active provider → the env var its key lives in (mirrors slash._PROVIDERS names).
_PROVIDER_KEY = {
    "deepseek": "DEEPSEEK_API_KEY",
    "deepseek-pro": "DEEPSEEK_API_KEY",
    "sonnet": "ANTHROPIC_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "haiku": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",  # extraction-only gateway (CLAUDE.md carve-out)
}


# Settings (model-per-role selections, budget) live in the palimpsest.db `settings`
# table — the SAME db as the cost ledger, so a run shares one source of truth. Keys
# stay in .env (set_value); selections go here. db_path defaults to the canonical
# repo ledger; tests pass a tmp path (canonical_db lets absolute paths through).
def _settings_conn(db_path: str) -> sqlite3.Connection:
    # A short-lived connection per call. busy_timeout so a /use write from the TUI
    # worker thread waits briefly rather than erroring if the agent loop is mid-write
    # on the shared palimpsest.db (CostMeter holds its own long-lived connection).
    conn = sqlite3.connect(canonical_db(db_path))
    conn.execute("PRAGMA busy_timeout = 3000")
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def get_setting(key: str, default: str | None = None, db_path: str = "palimpsest.db") -> str | None:
    conn = _settings_conn(db_path)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row and row[0] is not None else default
    finally:
        conn.close()


def set_setting(key: str, value: str, db_path: str = "palimpsest.db") -> str:
    conn = _settings_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        conn.commit()
        return value
    finally:
        conn.close()


def _env_path() -> Path:
    return workspace_root() / ".env"


def load(workspace: Path | None = None) -> None:
    """Load env from cwd ``.env`` (dev) then the workspace ``.env`` (spawn model).

    ``load_dotenv`` never overrides an already-set var, so loading the workspace
    ``.env`` FIRST makes it win for the spawn model; the cwd ``.env`` then fills
    any gaps (dev convenience) without shadowing the workspace.
    """
    env = (workspace / ".env") if workspace is not None else _env_path()
    if env.exists():
        load_dotenv(env)  # workspace first → wins
    load_dotenv()  # cwd/.env — fills gaps, never overrides the workspace


def set_value(key: str, value: str) -> str:
    """Persist ``KEY=value`` to the workspace ``.env`` (+ live ``os.environ``)."""
    os.environ[key] = value
    path = _env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = []
    if path.exists():
        kept = [ln for ln in path.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith(f"{key}=")]
    kept.append(f"{key}={value}")
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return f"saved {key} to {path}"


def ensure_llm_credentials(provider: str = "deepseek", prompt=getpass.getpass) -> None:
    """Ensure the active provider's API key is present; prompt + save if missing.

    Runs at startup AFTER ``ensure_repo`` (so the workspace ``.gitignore`` already
    excludes ``.env``) and BEFORE the agent is built. ``prompt`` is injectable for
    tests; the default hides input.
    """
    key = _PROVIDER_KEY.get(provider, "DEEPSEEK_API_KEY")
    if os.environ.get(key, "").strip():  # treat whitespace-only as absent
        return
    value = prompt(f"{key} is not set — paste it (hidden, saved to the workspace .env): ").strip()
    if value:
        set_value(key, value)
    else:
        # Don't silently proceed into the cryptic SDK auth error this guards against.
        print(f"warning: no {key} provided — set it later with /config set {key} <key>.")


def ensure_role_credentials(db_path: str = "palimpsest.db", prompt=getpass.getpass) -> None:
    """Ensure keys for the configured orchestration + extraction providers (app phase).

    Both roles may run on different providers, so a single key check isn't enough.
    Same provider for both (the default deepseek/deepseek) → one check. Called by the
    entry points before the agent is built.
    """
    roles = [
        get_setting("orchestration_model", "deepseek", db_path=db_path) or "deepseek",
        get_setting("extraction_model", "deepseek", db_path=db_path) or "deepseek",
    ]
    # De-dupe by the env var, not the provider name: sonnet and anthropic share
    # ANTHROPIC_API_KEY, so checking both would prompt twice for one missing key.
    seen: set[str] = set()
    for provider in roles:
        key = _PROVIDER_KEY.get(provider, "DEEPSEEK_API_KEY")
        if key in seen:
            continue
        seen.add(key)
        ensure_llm_credentials(provider, prompt=prompt)
