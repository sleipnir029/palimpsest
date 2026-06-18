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
from pathlib import Path

from dotenv import load_dotenv

from .policy import workspace_root

# Active provider → the env var its key lives in (mirrors slash._PROVIDERS names).
_PROVIDER_KEY = {
    "deepseek": "DEEPSEEK_API_KEY",
    "sonnet": "ANTHROPIC_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


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
