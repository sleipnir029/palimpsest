"""Process-global progress sink for long compound tools (B1).

Compound tools (``extract_paper`` → parse → extract → insert) are opaque single
calls; the human otherwise stares at "· working…" for the minutes a GPU parse
takes. The pipeline calls ``emit()`` at each stage boundary; the agent points the
sink at its event channel for the duration of a run, so the TUI shows live stages.

ponytail: a module-global sink, not a threaded callback — only one agent run is
ever in flight (the TUI disables input during a turn), so there is no concurrency.
If concurrent runs are ever needed, thread a callback through run_paper instead.
"""

from __future__ import annotations

from collections.abc import Callable

_sink: Callable[[str], None] | None = None


def set_sink(fn: Callable[[str], None] | None) -> None:
    """Install (or clear, with None) the progress sink. The agent owns its lifecycle."""
    global _sink
    _sink = fn


def emit(message: str) -> None:
    """Report a stage message, best-effort — never break the pipeline."""
    if _sink is None:
        return
    try:
        _sink(message)
    except Exception:  # noqa: BLE001 — progress must never break a run
        pass
