"""T32 — open_notebook tool tests (offline, Popen mocked).

No real marimo subprocess is spawned: a fake Popen records the call args and
replays a canned stdout stream so we can assert the file is written, the args
are right, and the URL is parsed back out.
"""

from __future__ import annotations

import subprocess
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
    """Run each test in a throwaway CWD with a `notebooks/` dir; mock Popen."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notebooks").mkdir()
    _FakePopen.instances = []
    monkeypatch.setattr(mod.subprocess, "Popen", _FakePopen)
    yield


def test_writes_content_to_named_path():
    open_notebook("over_nb", content="import marimo as mo\n")
    written = Path("notebooks/over_nb.py")
    assert written.read_text() == "import marimo as mo\n"


def test_copies_template_when_content_is_none():
    Path("notebooks/_template_default.py").write_text("# default template\n")
    open_notebook("from_tpl")
    assert Path("notebooks/from_tpl.py").read_text() == "# default template\n"


def test_popen_called_with_marimo_edit_headless_port_zero():
    open_notebook("argcheck", content="x = 1\n")
    assert len(_FakePopen.instances) == 1
    proc = _FakePopen.instances[0]
    assert proc.args == [
        "marimo",
        "edit",
        "notebooks/argcheck.py",
        "--headless",
        "--port",
        "0",
    ]


def test_returns_parsed_localhost_url():
    url = open_notebook("urlcheck", content="x = 1\n")
    assert url == "http://localhost:2718?access_token=tok123"


def test_content_takes_precedence_over_template():
    # Both given: content wins, template is never consulted (so a missing
    # template must NOT raise). Pins the card's "if content provided: write" order.
    open_notebook("both", content="from_content\n", template="does_not_exist")
    assert Path("notebooks/both.py").read_text() == "from_content\n"


def test_missing_template_raises():
    with pytest.raises(FileNotFoundError):
        open_notebook("nope", template="does_not_exist")


def test_marimo_dying_before_url_raises(monkeypatch):
    """stdout closes without ever announcing a URL → fail loudly, don't hang silently."""

    class _DeadPopen(_FakePopen):
        stdout_lines = ["startup failed\n"]  # no URL line, then EOF

    monkeypatch.setattr(mod.subprocess, "Popen", _DeadPopen)
    with pytest.raises(RuntimeError):
        open_notebook("dead", content="x = 1\n")
