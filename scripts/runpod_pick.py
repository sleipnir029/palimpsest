#!/usr/bin/env python
"""Interactive RunPod community-GPU picker for palimpsest parser pods.

Lists community GPUs that are rentable RIGHT NOW and meet our criteria
(VRAM >= floor), sorted cheapest-first, lets you pick one, and creates a pod from a
parser template. If creation fails (the GPU was snatched in the gap between listing
and confirming, or the host has no resources), it re-fetches and re-prompts.

Why two APIs: RunPod's REST API (stable) has no pre-flight availability query, so the
listing uses the GraphQL API (`gpuTypes { lowestPrice(...) }` — the only place stock is
exposed), while pod *creation* uses the stable REST API. If GraphQL is ever retired the
listing breaks but creation still works. Availability is best-effort even via GraphQL,
which is the whole reason for the retry loop.

This is a standalone ops helper, NOT part of the palimpsest agent. Reads RUNPOD_API_KEY
from .env. No new dependencies (httpx, rich, python-dotenv are already in pixi.toml).

Usage:
    pixi run python scripts/runpod_pick.py --template <TEMPLATE_ID>
    pixi run python scripts/runpod_pick.py --template <ID> --min-vram 12 --disk 30
"""
from __future__ import annotations

import argparse
import os

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

GQL_URL = "https://api.runpod.io/graphql"
REST_URL = "https://rest.runpod.io/v1"
console = Console()

# Community on-demand availability per GPU type. lowestPrice(secureCloud:false) returns a
# non-null uninterruptablePrice only when an on-demand community instance is rentable now.
GPU_TYPES_QUERY = """
query GpuTypes {
  gpuTypes {
    id
    displayName
    memoryInGb
    lowestPrice(input: {gpuCount: 1, secureCloud: false}) {
      uninterruptablePrice
      stockStatus
    }
  }
}
"""


def fetch_available(api_key: str, min_vram: int) -> list[dict]:
    """Return community GPUs rentable now with VRAM >= min_vram, cheapest-first."""
    resp = httpx.post(
        GQL_URL, params={"api_key": api_key}, json={"query": GPU_TYPES_QUERY}, timeout=30.0
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL error: {payload['errors']}")

    rows: list[dict] = []
    for g in payload["data"]["gpuTypes"]:
        # lowestPrice is already scoped to secureCloud:false, so a non-null on-demand
        # price here means an on-demand COMMUNITY instance is rentable right now.
        price = (g.get("lowestPrice") or {}).get("uninterruptablePrice")
        if price is None:
            continue
        if (g.get("memoryInGb") or 0) < min_vram:
            continue  # below our VRAM floor
        rows.append(
            {
                "id": g["id"],
                "name": g["displayName"],
                "vram": g["memoryInGb"],
                "price": price,
                "stock": (g.get("lowestPrice") or {}).get("stockStatus") or "?",
            }
        )
    rows.sort(key=lambda r: (r["price"], r["vram"]))
    return rows


def render(rows: list[dict], min_vram: int) -> None:
    table = Table(title=f"Community GPUs available now (VRAM ≥ {min_vram} GB, cheapest first)")
    table.add_column("#", justify="right")
    table.add_column("GPU")
    table.add_column("VRAM", justify="right")
    table.add_column("$/hr", justify="right")
    table.add_column("stock")
    for i, r in enumerate(rows, 1):
        table.add_row(str(i), r["name"], f"{r['vram']} GB", f"${r['price']:.3f}", str(r["stock"]))
    console.print(table)


def create_pod(api_key: str, template_id: str, gpu_id: str, disk: int) -> httpx.Response:
    body = {
        "templateId": template_id,
        "gpuTypeIds": [gpu_id],
        "cloudType": "COMMUNITY",
        "gpuCount": 1,
        "containerDiskInGb": disk,
    }
    return httpx.post(
        f"{REST_URL}/pods",
        headers={"Authorization": f"Bearer {api_key}"},
        json=body,
        timeout=60.0,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Interactive RunPod community-GPU picker.")
    ap.add_argument("--template", required=True, help="RunPod template id to launch the pod from")
    ap.add_argument("--min-vram", type=int, default=12, help="VRAM floor in GB (default 12)")
    ap.add_argument("--disk", type=int, default=30, help="container disk GB (default 30)")
    args = ap.parse_args()

    load_dotenv()
    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        console.print("[red]RUNPOD_API_KEY not set[/red] (put it in .env)")
        return 1

    while True:
        try:
            rows = fetch_available(api_key, args.min_vram)
        except Exception as e:  # noqa: BLE001 - surface any fetch/transport error to the user
            console.print(f"[red]availability fetch failed:[/red] {e}")
            if Prompt.ask("retry?", choices=["y", "n"], default="y") == "n":
                return 1
            continue

        if not rows:
            console.print(f"[yellow]No community GPUs ≥ {args.min_vram} GB rentable right now.[/yellow]")
            if Prompt.ask("re-fetch?", choices=["y", "n"], default="y") == "n":
                return 0
            continue

        render(rows, args.min_vram)
        sel = Prompt.ask("pick # to launch ('r' re-fetch, 'q' quit)", default="1")
        if sel == "q":
            return 0
        if sel == "r":
            continue
        try:
            chosen = rows[int(sel) - 1]
        except (ValueError, IndexError):
            console.print("[red]invalid choice[/red]")
            continue

        console.print(f"creating pod on [bold]{chosen['name']}[/bold] (${chosen['price']:.3f}/hr)…")
        try:
            resp = create_pod(api_key, args.template, chosen["id"], args.disk)
        except httpx.HTTPError as e:
            # The request itself failed mid-flight — a pod MIGHT have been created. Do not
            # auto-loop into another create (that could spawn a second paid pod).
            console.print(f"[red]create request errored:[/red] {e}")
            console.print("[yellow]Check the RunPod console for a created pod before retrying.[/yellow]")
            if Prompt.ask("retry anyway?", choices=["y", "n"], default="n") == "n":
                return 1
            continue

        if 200 <= resp.status_code < 300:
            # ANY 2xx means a pod was (probably) created — never fall through to re-create,
            # or we could spawn a second paid pod. Parse defensively: if the body is
            # unreadable the pod may still exist, so warn loudly rather than crash or retry.
            try:
                pod_id = resp.json().get("id")
            except ValueError:  # JSONDecodeError subclasses ValueError
                console.print(
                    "[yellow]Pod likely CREATED but the response was unreadable — check the "
                    "RunPod console and stop it if unneeded.[/yellow]"
                )
                return 1
            console.print(f"[green]pod created[/green]: id={pod_id} on {chosen['name']}")
            console.print("[dim]remember to stop it when done — cost discipline.[/dim]")
            return 0

        # Non-2xx => no pod created (e.g. snatched / no resources) => safe to re-fetch & retry.
        console.print(f"[red]create failed ({resp.status_code})[/red]: {resp.text}")
        console.print("[dim]likely taken in the meantime — re-fetching availability…[/dim]")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        console.print("\n[dim]cancelled[/dim]")
        raise SystemExit(0)
