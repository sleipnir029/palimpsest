"""SessionMonitor — a passive supervisor for watching a live agent session.

The agent already exposes two best-effort hooks: ``on_event`` (T63, fires a
``tool_call``/``tool_result`` dict per dispatch) and the ``SessionLog`` transcript
(T66). What neither gives you, while a demo is running, is the *debugging* view —
the three signals stitched together: tool traces with timing, per-prompt € spend,
and any exception that aborted a turn. ``SessionMonitor`` is that view.

It is purely observational (mirrors the ``_emit`` contract: a faulty observer must
never alter the loop), so wiring it changes nothing about how the agent behaves —
it only *records*. Both entrypoints use it: ``scripts/demo_monitor.py`` drives a
scripted run, and the TUI chains ``observe`` behind its own live trace. Output goes
to ``<workspace>/.palimpsest/demo-<ts>.{log,jsonl}`` — the same gitignored dir the
session transcript lives in, durable and never committed.

Unlike ``SessionLog`` this is NOT gated on a git workspace: the whole point is to
capture a demo run wherever it happens, so it always writes to its ``log_dir``.
"""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime
from pathlib import Path

from .cost import BudgetExceeded
from .policy import workspace_root

# €-spend marks worth calling out in the digest (mirrors the TUI's warn ladder).
_BUDGET_MARKS = (10, 20, 30, 40, 50)


class SessionMonitor:
    """Observe an agent session: log tool traces + cost, surface issues."""

    def __init__(self, log_dir: Path | str | None = None, echo: bool = True) -> None:
        # echo=False for the TUI: a stray print() would corrupt the Textual screen,
        # so there it only writes the files; the script keeps echo on for a live tail.
        self.echo = echo
        base = Path(log_dir) if log_dir is not None else workspace_root() / ".palimpsest"
        base.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = base / f"demo-{stamp}.log"
        self.jsonl_path = base / f"demo-{stamp}.jsonl"

        self.issues: list[dict] = []   # tool_error / exception / budget records
        self.runs: list[dict] = []     # one per monitor.run(): prompt, cost, ok, ...
        self.tool_timings: list[tuple[str, float]] = []
        self._pending: tuple[str, float] | None = None  # (tool name, start) — serial loop
        self._last_total: float | None = None

    # --- observation -------------------------------------------------------
    def observe(self, event: dict) -> None:
        """on_event-compatible callable. Logs each tool call/result; flags errors.

        Tool dispatch is serial in the loop (a ``for`` over tool_calls), so a single
        pending (name, start) is enough to time each call without per-id bookkeeping.
        """
        # Read defensively (match agent.py's own .get discipline): a raise here is
        # swallowed by Agent._emit, which would silently drop this trace and every
        # later one in the turn — the opposite of what a monitor is for.
        name = event.get("name", "?")
        if event.get("type") == "tool_call":
            args = ", ".join(f"{k}={v}" for k, v in (event.get("input") or {}).items())
            self._pending = (name, time.monotonic())
            self._log(f"→ {name}({args})", event)
            return

        # tool_result
        elapsed = 0.0
        if self._pending is not None:
            elapsed = time.monotonic() - self._pending[1]
            self.tool_timings.append((self._pending[0], elapsed))
            self._pending = None
        content = str(event.get("content", ""))
        snippet = content if len(content) <= 200 else content[:200] + "…"
        if event.get("is_error"):
            self.issues.append({"kind": "tool_error", "tool": name, "detail": content})
            self._log(f"✗ [{name} {elapsed:.2f}s] {snippet}", {**event, "elapsed_s": elapsed})
        else:
            self._log(f"← [{name} {elapsed:.2f}s] {snippet}", {**event, "elapsed_s": elapsed})

    # --- a single supervised turn -----------------------------------------
    def run(self, agent, prompt: str) -> str:
        """Wrap one ``agent.run(prompt)``: time it, meter the € delta, catch failures.

        Returns the agent's reply, or an ``[error] ...`` string if the turn raised —
        the exception is recorded as an issue rather than propagated, so a scripted
        demo sequence keeps going.
        """
        self._pending = None  # don't carry a dangling tool_call's start into this run
        before = agent.cost_meter.total_eur()
        self._log(f"\n>>> {prompt}", {"type": "prompt", "prompt": prompt})
        start = time.monotonic()
        ok, error, reply = True, None, ""
        try:
            reply = agent.run(prompt)
        except BudgetExceeded as exc:
            # The €-cap refusal is the project's headline failure mode — tag it
            # distinctly so the digest reads "budget", not a generic exception.
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            self.issues.append({"kind": "budget", "prompt": prompt, "detail": str(exc)})
            self._log(f"!!! {error}", {"type": "budget", "detail": error})
            reply = f"[budget] {error}"
        except Exception as exc:  # noqa: BLE001 — the monitor surfaces, never crashes the demo
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            self.issues.append({"kind": "exception", "prompt": prompt, "detail": error})
            self._log(f"!!! {error}\n{traceback.format_exc()}", {"type": "exception", "detail": error})
            reply = f"[error] {error}"
        seconds = time.monotonic() - start
        after = agent.cost_meter.total_eur()
        cost = round(after - before, 4)
        self._note_budget(after)
        self.runs.append({"prompt": prompt, "cost_eur": cost, "ok": ok, "error": error, "seconds": round(seconds, 2)})
        self._log(
            f"<<< {'ok' if ok else 'FAILED'} · €{cost:.4f} · {seconds:.1f}s · total €{after:.4f}",
            {"type": "run", "cost_eur": cost, "ok": ok, "seconds": round(seconds, 2), "total_eur": round(after, 4)},
        )
        return reply

    def _note_budget(self, total: float) -> None:
        """Record when cumulative spend crosses a warn mark since the last check."""
        prev = self._last_total if self._last_total is not None else 0.0
        for mark in _BUDGET_MARKS:
            if prev < mark <= total:
                self.issues.append({"kind": "budget", "detail": f"spend crossed €{mark} (now €{total:.2f})"})
        self._last_total = total

    # --- digest ------------------------------------------------------------
    def summary(self) -> str:
        n_tool = sum(1 for i in self.issues if i["kind"] == "tool_error")
        n_exc = sum(1 for i in self.issues if i["kind"] == "exception")
        n_budget = sum(1 for i in self.issues if i["kind"] == "budget")
        total = sum(r["cost_eur"] for r in self.runs)
        slowest = sorted(self.tool_timings, key=lambda t: t[1], reverse=True)[:3]
        lines = [
            "── session summary ─────────────────────────────",
            f"prompts: {len(self.runs)}  ·  spend: €{total:.4f}",
            f"issues: {n_tool} tool errors, {n_exc} exceptions, {n_budget} budget warnings",
        ]
        if slowest:
            lines.append("slowest tools: " + ", ".join(f"{n} {s:.2f}s" for n, s in slowest))
        for i in self.issues:
            lines.append(f"  · [{i['kind']}] {i.get('tool', '')} {i['detail']}".rstrip())
        lines.append(f"log: {self.log_path}")
        return "\n".join(lines)

    # --- sinks -------------------------------------------------------------
    def _log(self, human: str, record: dict) -> None:
        """Append to the human log + jsonl and echo to stdout (best-effort).

        Every jsonl record is stamped with an absolute ISO timestamp at this single
        chokepoint, so all event kinds (tool_call/result, prompt, run, exception,
        budget) carry ``ts`` for timeline/latency analysis across a stress run.
        """
        ts = datetime.now().isoformat(timespec="milliseconds")
        try:
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"{ts}  {human}\n")
            with self.jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": ts, **record}, default=str) + "\n")
        except Exception:  # noqa: BLE001 — logging must never break the demo
            pass
        if self.echo:
            print(human, flush=True)
