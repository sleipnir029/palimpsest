"""Tests for config/secrets bootstrap + the 'ask, don't invent' wiring.

Covers: workspace .env load/save, the startup credential prompt, the two
secret-leak guards (.env never committed by versioning, never writable by the
agent's tools), the /config command, and extract_paper's friendly missing-RunPod
message.
"""

from __future__ import annotations

import os

import pytest
from dulwich import porcelain
from dulwich.repo import Repo

from palimpsest import config, versioning
from palimpsest.policy import PolicyViolation, assert_writable


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    return tmp_path


# --- load / set_value -------------------------------------------------------

def test_load_reads_workspace_env(ws, monkeypatch):
    monkeypatch.delenv("PALIMP_SYNTH", raising=False)
    (ws / ".env").write_text("PALIMP_SYNTH=hello\n", encoding="utf-8")
    # Neutralize the cwd (.env) load so the repo's real secrets don't leak into the
    # shared test session (which would un-gate the live e2e test); keep the explicit
    # workspace-path load — the behavior under test.
    from dotenv import load_dotenv as _ld

    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: (_ld(*a, **k) if a else None))
    config.load()
    assert os.environ["PALIMP_SYNTH"] == "hello"


def test_set_value_writes_env_file_and_environ(ws, monkeypatch):
    monkeypatch.delenv("PALIMP_FOO", raising=False)
    config.set_value("PALIMP_FOO", "bar")
    assert os.environ["PALIMP_FOO"] == "bar"
    assert "PALIMP_FOO=bar" in (ws / ".env").read_text()


def test_set_value_replaces_existing_key(ws, monkeypatch):
    monkeypatch.delenv("PALIMP_FOO", raising=False)
    (ws / ".env").write_text("PALIMP_FOO=old\nOTHER=keep\n", encoding="utf-8")
    config.set_value("PALIMP_FOO", "new")
    body = (ws / ".env").read_text()
    assert "PALIMP_FOO=new" in body and "PALIMP_FOO=old" not in body
    assert "OTHER=keep" in body  # untouched


# --- ensure_llm_credentials -------------------------------------------------

def test_prompts_and_saves_when_key_missing(ws, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config.ensure_llm_credentials(prompt=lambda _msg: "sk-abc123")
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-abc123"
    assert "DEEPSEEK_API_KEY=sk-abc123" in (ws / ".env").read_text()


def test_noop_when_key_present(ws, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "already-set")

    def _boom(_msg):
        raise AssertionError("must not prompt when the key is present")

    config.ensure_llm_credentials(prompt=_boom)  # no raise == pass


# --- secret-leak guards -----------------------------------------------------

def test_env_is_never_committed_by_versioning(ws):
    versioning.ensure_repo()                      # writes .gitignore (now incl .env)
    config.set_value("DEEPSEEK_API_KEY", "secret")  # writes workspace/.env
    (ws / "notes.md").write_text("public", encoding="utf-8")
    versioning.checkpoint("turn")
    tracked = {p.decode() for p in porcelain.ls_files(Repo(str(ws)))}
    assert "notes.md" in tracked          # ordinary content is committed
    assert ".env" not in tracked          # the secret is not


def test_env_appended_to_pre_existing_gitignore(ws):
    # B1: an older workspace already has a .gitignore lacking .env — ensure_repo
    # must add it, or the per-action checkpoint would commit secrets.
    (ws / ".gitignore").write_text("config.txt\n*.db\nstore/\ncache/\n", encoding="utf-8")
    versioning.ensure_repo()
    config.set_value("DEEPSEEK_API_KEY", "SUPER-SECRET")
    (ws / "notes.md").write_text("public", encoding="utf-8")
    versioning.checkpoint("turn")
    tracked = {p.decode() for p in porcelain.ls_files(Repo(str(ws)))}
    assert "notes.md" in tracked and ".env" not in tracked


def test_env_is_refused_by_write_policy(ws):
    with pytest.raises(PolicyViolation, match="protected"):
        assert_writable(str(ws / ".env"))


def test_set_value_does_not_drop_prefix_collision(ws, monkeypatch):
    # 'KEY=' filter must not also drop 'KEY2=...'
    monkeypatch.delenv("PALIMP_K", raising=False)
    (ws / ".env").write_text("PALIMP_K2=keep\n", encoding="utf-8")
    config.set_value("PALIMP_K", "v")
    body = (ws / ".env").read_text()
    assert "PALIMP_K2=keep" in body and "PALIMP_K=v" in body


# --- /config command --------------------------------------------------------

def test_config_command_shows_masked_status(ws, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    from palimpsest.tui.slash import _config

    out = _config(app=None, args=[])
    assert "DEEPSEEK_API_KEY=set" in out
    assert "RUNPOD_API_KEY=(unset)" in out


def test_config_set_provider_key_reloads_provider(ws, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from types import SimpleNamespace

    from palimpsest.tui.slash import _config

    app = SimpleNamespace(agent=SimpleNamespace(provider=None))
    out = _config(app, ["set", "DEEPSEEK_API_KEY", "sk-xyz"])
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-xyz"
    assert app.agent.provider is not None and app.agent.provider.name == "deepseek-v4-flash"
    assert "reloaded" in out


# --- extract_paper: friendly missing-RunPod message -------------------------

def test_extract_paper_missing_runpod_is_actionable(monkeypatch):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    import palimpsest.cost as cost_mod
    import palimpsest.pipeline as pipeline_mod
    import palimpsest.store as store_mod

    def _needs_runpod(*a, **k):
        raise KeyError("RUNPOD_API_KEY")

    monkeypatch.setattr(pipeline_mod, "run_paper", _needs_runpod)
    monkeypatch.setattr(store_mod, "RDFStore", lambda path: None)
    monkeypatch.setattr(cost_mod, "CostMeter", lambda path: None)
    from palimpsest.tools.run_paper import extract_paper

    out = extract_paper("papers/new.pdf")
    assert "missing config: RUNPOD_API_KEY" in out
    assert "/config set RUNPOD_API_KEY" in out


def test_extract_paper_does_not_mislabel_unrelated_keyerror(monkeypatch):
    # B2: an unrelated KeyError (a real bug) must NOT be reported as missing RunPod,
    # even when RUNPOD_API_KEY is unset (the normal cached-parse state).
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    import palimpsest.cost as cost_mod
    import palimpsest.pipeline as pipeline_mod
    import palimpsest.store as store_mod

    def _bug(*a, **k):
        raise KeyError("some_internal_dict_key")

    monkeypatch.setattr(pipeline_mod, "run_paper", _bug)
    monkeypatch.setattr(store_mod, "RDFStore", lambda path: None)
    monkeypatch.setattr(cost_mod, "CostMeter", lambda path: None)
    from palimpsest.tools.run_paper import extract_paper

    with pytest.raises(KeyError, match="some_internal_dict_key"):
        extract_paper("papers/new.pdf")
