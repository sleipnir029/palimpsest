"""Render every TUI theme to an SVG and build a browsable HTML gallery.

    Run:   pixi run python scripts/preview_themes.py
    Open:  open theme-preview/index.html

Each theme renders the SAME sample conversation so they're directly comparable.
Output (theme-preview/) is gitignored — regenerate any time after tweaking themes.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]  # find `palimpsest` + the `schema` namespace pkg
os.environ.setdefault("PALIMPSEST_WORKSPACE", tempfile.mkdtemp())

from palimpsest.cost import CostMeter  # noqa: E402
from palimpsest.tui.app import PalimpsestApp  # noqa: E402
from palimpsest.tui.themes import THEMES  # noqa: E402

OUT = ROOT / "theme-preview"
OUT.mkdir(exist_ok=True)

_REPLY = (
    "## Extracted 19 measurements from paper1\n\n"
    "- **Overpotential** — 236 mV  *(η10 = 236 mV vs RHE, p4)*\n"
    "- **Tafel slope** — 41 mV/dec\n"
    "- **Mass activity** — 1.2 A/mg\n\n"
    "All inserted into the graph with full provenance. Query them with `sparql_query`."
)


class _Demo:
    """Scripted agent: emits a tool call+result, then a markdown reply."""

    def __init__(self, meter: CostMeter) -> None:
        self.cost_meter = meter
        self.on_event = None

    def run(self, text: str) -> str:
        if self.on_event:
            self.on_event({"type": "tool_call", "name": "extract_paper",
                           "input": {"pdf_path": "papers/ir-co3o4.pdf", "parser_name": "mineru"}})
            self.on_event({"type": "tool_result", "name": "extract_paper",
                           "content": '{"n_extracted": 19, "n_inserted": 19, "dropped": 0}',
                           "is_error": False})
        self.cost_meter.record_llm("deepseek", 0.0084)
        return _REPLY


async def _render(name: str) -> None:
    meter = CostMeter(tempfile.mktemp(suffix=".db"))
    app = PalimpsestApp(agent=_Demo(meter), cost_meter=meter)
    async with app.run_test(size=(94, 30)) as pilot:
        app.theme = name
        app._refresh_topbar()  # on_mount set the topbar to the default; reflect this theme
        app.query_one("#prompt").value = "extract papers/ir-co3o4.pdf"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        app.save_screenshot(str(OUT / f"{name}.svg"))


def _swatches(theme) -> str:
    return "".join(
        f'<span class="sw" style="background:{getattr(theme, k)}" title="{k}: {getattr(theme, k)}"></span>'
        for k in ("background", "foreground", "primary", "secondary", "accent")
    )


def _html() -> str:
    cards = "".join(
        f'''
      <section class="card">
        <header><h2>{name}</h2><div class="sw-row">{_swatches(theme)}</div></header>
        <img src="{name}.svg" alt="{name} theme preview">
      </section>'''
        for name, theme in THEMES.items()
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>palimpsest — TUI themes</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; padding:2rem; background:#0b0b0d; color:#d8d8d8;
         font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  h1 {{ font-weight:600; letter-spacing:.02em; margin:0 0 .25rem; }}
  p.hint {{ color:#8a8a8a; margin:0 0 1.5rem; }}
  code {{ background:#1c1c20; padding:.1em .4em; border-radius:4px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(460px,1fr)); gap:1.5rem; }}
  .card {{ background:#141416; border:1px solid #26262a; border-radius:10px; overflow:hidden; }}
  .card header {{ display:flex; align-items:center; justify-content:space-between;
                 padding:.6rem 1rem; border-bottom:1px solid #26262a; }}
  .card h2 {{ margin:0; font-size:1rem; font-weight:600; text-transform:capitalize; }}
  .sw-row {{ display:flex; gap:.35rem; }}
  .sw {{ width:18px; height:18px; border-radius:5px; border:1px solid #0007; }}
  .card img {{ display:block; width:100%; height:auto; }}
</style></head>
<body>
  <h1>palimpsest · TUI theme variants</h1>
  <p class="hint">Same conversation in each theme. Switch live with <code>/theme &lt;name&gt;</code> (persisted in settings).</p>
  <div class="grid">{cards}</div>
</body></html>'''


async def _main() -> None:
    for name in THEMES:
        await _render(name)
        print("rendered", name)
    (OUT / "index.html").write_text(_html(), encoding="utf-8")
    print("gallery:", OUT / "index.html")


if __name__ == "__main__":
    asyncio.run(_main())
