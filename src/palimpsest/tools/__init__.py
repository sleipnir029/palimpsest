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
