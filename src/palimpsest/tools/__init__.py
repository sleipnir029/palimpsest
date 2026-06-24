"""Agent tools.

`TOOLS` is a module-level registry mapping tool name -> callable. Tools register
themselves at import time via the `@register` decorator; the agent loop looks a
tool up here by name to execute it. The Anthropic schema for each tool is stashed
on the function as `.tool_schema` so the agent can advertise it to the API.
"""

from __future__ import annotations

from collections.abc import Callable

TOOLS: dict[str, Callable] = {}


def register(name: str, schema: dict) -> Callable:
    """Decorator: add `fn` to TOOLS under `name`, attaching its Anthropic schema.

    `schema` is the tool body (`description`, `input_schema`); `name` is merged in.
    """

    def decorator(fn: Callable) -> Callable:
        fn.tool_schema = {"name": name, **schema}
        TOOLS[name] = fn
        return fn

    return decorator


from . import read_first_page_text  # noqa: E402,F401 — import for @register side effect
from . import read_paper  # noqa: E402,F401 — import for @register side effect
from . import read_skill  # noqa: E402,F401 — import for @register side effect
from . import check_skill  # noqa: E402,F401 — import for @register side effect
from . import reload_skills  # noqa: E402,F401 — import for @register side effect
from . import extract  # noqa: E402,F401 — import for @register side effect
from . import open_notebook  # noqa: E402,F401 — import for @register side effect
from . import read_file  # noqa: E402,F401 — import for @register side effect
from . import list_dir  # noqa: E402,F401 — import for @register side effect
from . import search  # noqa: E402,F401 — import for @register side effect
from . import sparql_query  # noqa: E402,F401 — import for @register side effect
from . import correct_measurement  # noqa: E402,F401 — import for @register side effect
from . import run_paper  # noqa: E402,F401 — import for @register side effect (registers extract_paper)
from . import write_file  # noqa: E402,F401 — import for @register side effect
from . import edit_file  # noqa: E402,F401 — import for @register side effect
from . import bash  # noqa: E402,F401 — import for @register side effect
from . import workspace_status  # noqa: E402,F401 — import for @register side effect
from . import extraction_report  # noqa: E402,F401 — import for @register side effect
from . import diagnose_run  # noqa: E402,F401 — import for @register side effect
from . import graph_summary  # noqa: E402,F401 — import for @register side effect (registers describe_schema + graph_summary)
