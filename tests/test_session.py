"""T66: persistent session transcript.

The agent appends every turn (user message, assistant turn incl. tool calls, and
tool results) to a git-tracked ``.palimpsest/session.jsonl`` in the workspace, so a
spawn leaves a durable record and a future session can reload context. Offline:
stub providers drive the loop deterministically, a tmp workspace stands in for the
real one (gated on ``ensure_repo`` having created ``.git``).
"""

from __future__ import annotations

import json

import pytest

from dulwich import porcelain
from dulwich.repo import Repo

from palimpsest import policy, versioning
from palimpsest.agent import Agent, MaxTurnsExceeded
from palimpsest.cost import CostMeter
from palimpsest.providers.anthropic import LLMResponse
from palimpsest.session import SessionLog
from palimpsest.tools.read_file import read_file

# A failing tool already registered by tests/test_agent.py at import; reuse it to
# drive the tool-call path.
from tests.test_agent import _AlwaysCallsToolProvider, always_fails

_ZERO_USAGE = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 0,
}


class _FinalAnswerProvider:
    """Stub provider: answers immediately with text, no tool calls (one turn)."""

    name = "stub"

    def __init__(self, text: str = "ok") -> None:
        self.text = text

    def complete(self, system, messages, tools, cache_breakpoints):
        return LLMResponse(
            text=self.text,
            tool_calls=[],
            usage=_ZERO_USAGE,
            raw={"content": [{"type": "text", "text": self.text}]},
        )


class _ReadsFileThenAnswers:
    """Turn 1: a read_file(path) tool call. Turn 2: a final answer. Drives the
    secret-redaction path with a real read_file dispatch."""

    name = "stub"

    def __init__(self, path: str) -> None:
        self.path = path
        self.calls = 0

    def complete(self, system, messages, tools, cache_breakpoints):
        self.calls += 1
        if self.calls == 1:
            call = {"id": "r1", "name": "read_file", "input": {"path": self.path}}
            return LLMResponse(
                text="", tool_calls=[call], usage=_ZERO_USAGE,
                raw={"content": [{"type": "tool_use", **call}]},
            )
        return LLMResponse(
            text="done", tool_calls=[], usage=_ZERO_USAGE,
            raw={"content": [{"type": "text", "text": "done"}]},
        )


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A tmp workspace with an initialized git repo (so the session gate is open)."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(versioning, "_last_tagged", None)
    monkeypatch.setattr(versioning, "_turn", 0)
    versioning.ensure_repo()
    return tmp_path


def _records(root):
    log = root / ".palimpsest" / "session.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _agent(provider, tmp_path, **kw):
    meter = CostMeter(str(tmp_path / "c.db"))
    return Agent(provider, meter, **kw)


def test_two_turns_logged(ws, tmp_path):
    """The card's target: two turns → the log holds both (user + assistant each)."""
    agent = _agent(_FinalAnswerProvider("first"), tmp_path)
    agent.run("hello")
    agent.run("again")

    recs = _records(ws)
    users = [r for r in recs if r["role"] == "user"]
    assistants = [r for r in recs if r["role"] == "assistant"]
    assert [r["content"] for r in users] == ["hello", "again"]
    assert len(assistants) == 2  # one assistant reply per turn


def test_tool_call_turn_logged(ws, tmp_path):
    """A turn with a tool call logs the assistant tool_use AND the tool result —
    i.e. 'tool calls + results' from the card are both captured."""
    agent = _agent(
        _AlwaysCallsToolProvider(),
        tmp_path,
        tools={"always_fails": always_fails.tool_schema},
        max_turns=1,
    )
    with pytest.raises(MaxTurnsExceeded):
        agent.run("do it")

    recs = _records(ws)
    # user prompt, assistant tool_use, tool_result (user role) — three records.
    assert recs[0] == {"role": "user", "content": "do it"}
    assistant = recs[1]
    assert assistant["role"] == "assistant"
    assert any(b.get("type") == "tool_use" for b in assistant["content"])
    tool_result = recs[2]
    assert tool_result["role"] == "user"
    assert tool_result["content"][0]["type"] == "tool_result"


def test_no_workspace_no_write(tmp_path, monkeypatch):
    """No ensure_repo → no .git → the gate skips: nothing is written (no pollution)."""
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    agent = _agent(_FinalAnswerProvider(), tmp_path)
    agent.run("hello")
    assert not (tmp_path / ".palimpsest" / "session.jsonl").exists()


def test_load_round_trips(ws, tmp_path):
    """SessionLog.load() returns the message dicts so a fresh agent can resume —
    the reload mechanism, demonstrated without wiring build_agent."""
    agent = _agent(_FinalAnswerProvider("answer"), tmp_path)
    agent.run("remember this")

    reloaded = SessionLog().load()
    assert {"role": "user", "content": "remember this"} in reloaded

    fresh = _agent(_FinalAnswerProvider(), tmp_path)
    fresh.messages = reloaded
    assert any(
        m["role"] == "user" and m["content"] == "remember this" for m in fresh.messages
    )


def test_load_limit_tails(ws, tmp_path):
    """load(limit=N) keeps only the last N records (tail for a bounded resume)."""
    agent = _agent(_FinalAnswerProvider(), tmp_path)
    agent.run("one")
    agent.run("two")

    full = SessionLog().load()
    assert len(full) == 4  # user/assistant × 2 turns
    assert SessionLog().load(limit=2) == full[-2:]  # the TAIL, not just any 2


def test_load_tolerates_truncated_tail(ws):
    """A process killed mid-append leaves a partial last line — the crash-then-resume
    case load() must survive. It skips the broken line instead of raising."""
    log = SessionLog()
    log.append({"role": "user", "content": "complete"})
    path = ws / ".palimpsest" / "session.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"role": "assistant", "content": [{"type": "te')  # truncated, no newline

    recs = log.load()  # must not raise
    assert recs == [{"role": "user", "content": "complete"}]


# --- secret redaction (caveat 3) -------------------------------------------------

def _tool_result_block(record):
    """The first tool_result block of a logged tool-result (user) record."""
    return record["content"][0]


def test_secret_read_redacted_in_log_but_real_in_memory(ws, tmp_path):
    """A read_file of a secret path: the persisted transcript carries a redaction
    marker (never the secret), while self.messages keeps the real content so the
    live session still functions."""
    (ws / ".env").write_text("ANTHROPIC_API_KEY=sk-supersecret", encoding="utf-8")
    agent = _agent(
        _ReadsFileThenAnswers(str(ws / ".env")),
        tmp_path,
        tools={"read_file": read_file.tool_schema},
    )
    agent.run("read the env")

    # On disk: the tool_result is redacted, the secret never appears anywhere.
    log_text = (ws / ".palimpsest" / "session.jsonl").read_text()
    assert "sk-supersecret" not in log_text
    tool_results = [
        r for r in _records(ws) if r["role"] == "user" and isinstance(r["content"], list)
    ]
    assert "redacted" in _tool_result_block(tool_results[0])["content"].lower()

    # In memory: the agent still has the real content (the live turn worked).
    mem = [
        m for m in agent.messages if m["role"] == "user" and isinstance(m["content"], list)
    ]
    assert "sk-supersecret" in _tool_result_block(mem[0])["content"]


class _TwoReadsThenAnswers:
    """Turn 1: two read_file calls (a secret + a normal file) in ONE turn. Turn 2:
    a final answer. Pins that redaction masks only the secret block."""

    name = "stub"

    def __init__(self, secret_path: str, public_path: str) -> None:
        self.secret_path = secret_path
        self.public_path = public_path
        self.calls = 0

    def complete(self, system, messages, tools, cache_breakpoints):
        self.calls += 1
        if self.calls == 1:
            calls = [
                {"id": "s1", "name": "read_file", "input": {"path": self.secret_path}},
                {"id": "p1", "name": "read_file", "input": {"path": self.public_path}},
            ]
            return LLMResponse(
                text="", tool_calls=calls, usage=_ZERO_USAGE,
                raw={"content": [{"type": "tool_use", **c} for c in calls]},
            )
        return LLMResponse(
            text="done", tool_calls=[], usage=_ZERO_USAGE,
            raw={"content": [{"type": "text", "text": "done"}]},
        )


def test_only_secret_block_redacted_in_a_mixed_turn(ws, tmp_path):
    """One turn, two reads: only the secret block is redacted; the normal one is
    logged verbatim (per-block redaction, not whole-message)."""
    (ws / ".env").write_text("KEY=sk-zzz", encoding="utf-8")
    (ws / "notes.md").write_text("public notes", encoding="utf-8")
    agent = _agent(
        _TwoReadsThenAnswers(str(ws / ".env"), str(ws / "notes.md")),
        tmp_path,
        tools={"read_file": read_file.tool_schema},
    )
    agent.run("read both")

    log_text = (ws / ".palimpsest" / "session.jsonl").read_text()
    assert "sk-zzz" not in log_text          # secret masked
    assert "public notes" in log_text        # normal content preserved


def test_non_secret_read_not_redacted(ws, tmp_path):
    """No false positives: a normal file's content is logged verbatim."""
    (ws / "notes.md").write_text("just some notes", encoding="utf-8")
    agent = _agent(
        _ReadsFileThenAnswers(str(ws / "notes.md")),
        tmp_path,
        tools={"read_file": read_file.tool_schema},
    )
    agent.run("read notes")

    tool_results = [
        r for r in _records(ws) if r["role"] == "user" and isinstance(r["content"], list)
    ]
    assert "just some notes" in _tool_result_block(tool_results[0])["content"]


def test_is_secret_path():
    assert policy.is_secret_path(".env")
    assert policy.is_secret_path("sub/dir/.env")
    assert policy.is_secret_path("config.txt")
    assert policy.is_secret_path("provider.key")
    assert not policy.is_secret_path("notes.md")
    assert not policy.is_secret_path("")
    assert not policy.is_secret_path("palimpsest.db")  # binary-refused, gitignored


# --- gitignore: transcript stays out of git (caveat 4) ---------------------------

def test_transcript_is_gitignored(ws, tmp_path):
    """The transcript is durable on disk but NOT git-tracked, so /undo can never
    truncate the append-only reflection record (caveat 4)."""
    agent = _agent(_FinalAnswerProvider(), tmp_path)
    agent.run("hello")
    versioning.checkpoint("would commit anything tracked")  # git add -A

    tracked = {
        p.decode() if isinstance(p, bytes) else p
        for p in porcelain.ls_files(Repo(str(ws)))
    }
    assert not any(".palimpsest" in t for t in tracked)  # never tracked
    assert (ws / ".palimpsest" / "session.jsonl").exists()  # but on disk
