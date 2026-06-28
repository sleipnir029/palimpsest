"""T32 — open_notebook tool tests (offline, Popen mocked).

No real marimo subprocess is spawned: a fake Popen records the call args and
replays a canned stdout stream so we can assert the file is written, the args
are right, and the URL is parsed back out.

Notebook *instances* are workspace artifacts (``<workspace>/notebooks/<name>.py``)
— the same place the agent's ``write_file`` can put them, so "build a notebook,
then open it" is coherent. Templates are engine assets at the repo-root
``notebooks/_template_*.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from palimpsest.tools import open_notebook as mod
from palimpsest.tools.open_notebook import open_notebook


class _FakePopen:
    """Records construction args; replays a stdout stream that announces a URL."""

    instances: list["_FakePopen"] = []
    stdout_lines = [
        "Starting marimo...\n",
        "        URL: http://localhost:2718?access_token=tok123\n",
    ]

    def __init__(self, args, stdout=None, stderr=None, text=None):
        self.args = args
        self.kwargs = {"stdout": stdout, "stderr": stderr, "text": text}
        self.stdout = iter(self.stdout_lines)
        _FakePopen.instances.append(self)

    def poll(self):
        return 1


@pytest.fixture(autouse=True)
def _in_tmp_repo(tmp_path, monkeypatch):
    """Throwaway repo: cwd has the engine ``notebooks/`` (templates); the workspace
    defaults to ``<cwd>/workspace``. Popen is mocked."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notebooks").mkdir()  # engine templates live here
    _FakePopen.instances = []
    mod._PROCESSES.clear()  # don't leak fakes into the atexit reaper / other tests
    monkeypatch.setattr(mod.subprocess, "Popen", _FakePopen)
    yield


def _ws_nb(name: str) -> Path:
    """The workspace path an instance should land at."""
    return Path("workspace/notebooks") / f"{name}.py"


def test_writes_content_to_workspace_path():
    open_notebook("over_nb", content="import marimo as mo\n")
    assert _ws_nb("over_nb").read_text() == "import marimo as mo\n"


def test_copies_template_when_content_is_none_and_no_existing():
    Path("notebooks/_template_default.py").write_text("# default template\n")
    open_notebook("from_tpl")
    assert _ws_nb("from_tpl").read_text() == "# default template\n"


def test_opens_existing_notebook_without_clobbering_with_template():
    """The bug fix: content omitted but the notebook already exists → open it as-is.
    A template must NOT overwrite the agent's own work."""
    _ws_nb("mine").parent.mkdir(parents=True, exist_ok=True)
    _ws_nb("mine").write_text("# the agent's real notebook\nrun_sparql(...)\n")
    Path("notebooks/_template_default.py").write_text("# generic template\n")

    open_notebook("mine")  # no content, no explicit template

    assert _ws_nb("mine").read_text() == "# the agent's real notebook\nrun_sparql(...)\n"
    assert _FakePopen.instances[0].args[2] == str(_ws_nb("mine").resolve())


def test_popen_called_with_marimo_edit_headless_port_zero():
    open_notebook("argcheck", content="x = 1\n")
    assert len(_FakePopen.instances) == 1
    proc = _FakePopen.instances[0]
    assert proc.args == [
        "marimo",
        "edit",
        str(_ws_nb("argcheck").resolve()),
        "--headless",
        "--port",
        "0",
    ]


def test_returns_parsed_localhost_url():
    url = open_notebook("urlcheck", content="x = 1\n")
    assert url == "http://localhost:2718?access_token=tok123"


def test_content_takes_precedence_over_template_and_existing():
    # Both given: content wins, template is never consulted (so a missing
    # template must NOT raise). Pins the card's "if content provided: write" order.
    open_notebook("both", content="from_content\n", template="does_not_exist")
    assert _ws_nb("both").read_text() == "from_content\n"


def test_missing_template_raises_when_no_existing():
    with pytest.raises(FileNotFoundError):
        open_notebook("nope", template="does_not_exist")


def test_rejects_path_traversal_in_name():
    """`name` is agent-controlled; it must not be able to escape the workspace via
    `..` — same code-enforced fence as write_file (routes through assert_writable)."""
    from palimpsest.policy import PolicyViolation

    with pytest.raises(PolicyViolation):
        open_notebook("../../escape", content="pwned\n")
    assert not Path("escape.py").exists()  # nothing written outside the workspace


def test_reap_notebooks_terminates_and_clears(monkeypatch):
    """reap_notebooks SIGTERMs running editors, SIGKILLs stragglers, empties the list."""

    class _Proc:
        def __init__(self, running: bool, hang: bool = False):
            self._running = running
            self._hang = hang
            self.terminated = self.killed = False

        def poll(self):
            return None if self._running else 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            if self._hang:
                raise mod.subprocess.TimeoutExpired(cmd="marimo", timeout=timeout)
            return 0

        def kill(self):
            self.killed = True

    running = _Proc(running=True)
    straggler = _Proc(running=True, hang=True)
    done = _Proc(running=False)
    monkeypatch.setattr(mod, "_PROCESSES", [running, straggler, done])

    mod.reap_notebooks()

    assert running.terminated and not running.killed   # terminated, exited cleanly
    assert straggler.terminated and straggler.killed   # hung → escalated to kill
    assert not done.terminated                         # already exited → left alone
    assert mod._PROCESSES == []                         # list drained


def test_marimo_dying_before_url_raises(monkeypatch):
    """stdout closes without ever announcing a URL → fail loudly, don't hang silently."""

    class _DeadPopen(_FakePopen):
        stdout_lines = ["startup failed\n"]  # no URL line, then EOF

    monkeypatch.setattr(mod.subprocess, "Popen", _DeadPopen)
    with pytest.raises(RuntimeError):
        open_notebook("dead", content="x = 1\n")
