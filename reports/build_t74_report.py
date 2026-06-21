#!/usr/bin/env python3
"""Build the self-contained T74 report (multi-pass & ensemble vs single-shot).

Reads experiments/results/{reachable.json, gold_thinness.json, llm_matrix_t74.csv,
llm_matrix_t74_<date>.meta.json} and bakes them into one static HTML file
(reports/t74_report.html). No runtime deps: server-rendered HTML + CSS bars.

Regenerate:  pixi run python reports/build_t74_report.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"
OUT = Path(__file__).resolve().parent / "t74_report.html"

CHEAP = ["deepseek-flash", "gemini-lite"]
ARMS = ["raw", "reason-first", "reason-first-16k", "union-k3", "requery", "judge"]
ARM_DESC = {
    "raw": "single-shot baseline (A)",
    "reason-first": "reason-then-format @8k (B)",
    "reason-first-16k": "reason-then-format @16k (B retest)",
    "union-k3": "3 samples, unioned (C)",
    "requery": "pass-1 + missing-type re-query (D)",
    "judge": "LLM-judge precision filter (F)",
}


def _load():
    reach = json.loads((RESULTS / "reachable.json").read_text())["rows"]
    gold = json.loads((RESULTS / "gold_thinness.json").read_text())["candidates"]
    rows = list(csv.DictReader((ROOT / "experiments" / "llm_matrix_t74.csv").open()))
    metas = sorted(RESULTS.glob("llm_matrix_t74_*.meta.json"))
    meta = json.loads(metas[-1].read_text()) if metas else {}
    return reach, gold, rows, meta


def _bar(pct: float, color: str) -> str:
    return (f'<div class="bar"><div class="fill" style="width:{pct:.0f}%;'
            f'background:{color}"></div><span>{pct:.0f}%</span></div>')


def _reach(reach, parser, label, mode):
    for r in reach:
        if r["parser"] == parser and r["label"] == label and r["mode"] == mode:
            return r
    return None


def build() -> str:
    reach, gold, rows, meta = _load()

    # Headline: model-union (from CSV) vs best frontier single-shot (from reachable raw).
    mu = {}
    for r in rows:
        if r["label"] == "model-union":
            p = r["parser"]; mu.setdefault(p, [0, 0])
            mu[p][0] += int(r["tp"]); mu[p][1] += int(r["gt_total"])
    mu_pct = {p: 100 * tp / gt for p, (tp, gt) in mu.items()}
    front = {p: max((_reach(reach, p, m, "raw") or {"recall": 0})["recall"]
                    for m in ("sonnet-4.6", "openai-frontier"))
             for p in ("docling", "paddle")}

    # Arms grid (reachable-recall per cheap model × parser × arm).
    grid_rows = ""
    for parser in ("docling", "paddle"):
        for label in CHEAP:
            cells = ""
            for arm in ARMS:
                r = _reach(reach, parser, label, arm)
                if r is None:
                    cells += '<td class="na">—</td>'
                    continue
                rr = r["reachable_recall"] * 100
                color = "#16a34a" if rr >= 95 else "#65a30d" if rr >= 85 else \
                        "#ca8a04" if rr >= 70 else "#dc2626"
                cells += f'<td>{_bar(rr, color)}</td>'
            grid_rows += f'<tr><td class="lbl">{parser}</td><td class="lbl">{label}</td>{cells}</tr>'

    # reason-first retest deltas (docling, deepseek the backfire case).
    rf = {a: _reach(reach, "docling", "deepseek-flash", a) for a in
          ("raw", "reason-first", "reason-first-16k")}
    rf_line = " → ".join(
        f'{ARM_DESC[a].split("(")[0].strip()}: <b>{rf[a]["recall"]*100:.0f}%</b>'
        for a in ("reason-first", "reason-first-16k", "raw") if rf[a])

    # gold-thinness buckets.
    real = [g for g in gold if g["n_models_agree"] >= 3]
    halluc = [g for g in gold if g["n_models_agree"] == 1]
    gold_rows = "".join(
        f'<tr><td>{g["type"]}</td><td class="num">{g["value"]}</td>'
        f'<td class="num">{g["sha8"]}</td><td class="num">{g["n_models_agree"]}</td></tr>'
        for g in real[:12])

    arm_cols = "".join(f'<th title="{ARM_DESC[a]}">{a}</th>' for a in ARMS)

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>T74 — Multi-pass & ensemble extraction</title>
<style>
  :root{{--ink:#1a1a1a;--mut:#666;--line:#e5e5e5;--bg:#fafafa}}
  *{{box-sizing:border-box}}
  body{{font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);
        max-width:960px;margin:0 auto;padding:2rem 1.25rem;background:#fff}}
  h1{{font-size:1.7rem;margin:0 0 .25rem}} h2{{font-size:1.2rem;margin:2.2rem 0 .6rem;
        border-bottom:2px solid var(--line);padding-bottom:.3rem}}
  .sub{{color:var(--mut);margin:0 0 1.5rem}}
  .hero{{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}}
  .card{{flex:1;min-width:200px;border:1px solid var(--line);border-radius:10px;
        padding:1rem 1.2rem;background:var(--bg)}}
  .card .big{{font-size:2rem;font-weight:700;color:#16a34a}}
  .card .lbl2{{color:var(--mut);font-size:.85rem}}
  table{{border-collapse:collapse;width:100%;margin:.5rem 0;font-size:13.5px}}
  th,td{{border:1px solid var(--line);padding:.4rem .55rem;text-align:left}}
  th{{background:var(--bg);font-weight:600}}
  td.lbl{{font-weight:600;white-space:nowrap}} td.num{{text-align:right;font-variant-numeric:tabular-nums}}
  td.na{{color:#bbb;text-align:center}}
  .bar{{position:relative;height:18px;background:#f0f0f0;border-radius:4px;min-width:90px}}
  .bar .fill{{height:100%;border-radius:4px}}
  .bar span{{position:absolute;left:6px;top:0;font-size:11px;line-height:18px;color:#fff;
        font-weight:600;text-shadow:0 0 2px rgba(0,0,0,.4)}}
  .note{{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:.8rem 1rem;
        margin:1rem 0;font-size:13.5px}}
  .verdict{{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:.8rem 1rem;margin:1rem 0}}
  code{{background:#f3f4f6;padding:.1rem .3rem;border-radius:3px;font-size:.85em}}
  .foot{{color:var(--mut);font-size:.8rem;margin-top:2.5rem;border-top:1px solid var(--line);padding-top:1rem}}
</style></head><body>

<h1>T74 — Multi-pass &amp; ensemble extraction vs single-shot</h1>
<p class="sub">Can a cheap model + a loop match an expensive model's single shot?
Built on the T72 gold (5 papers, 40 tuples) &amp; deterministic scorer. Spend fenced to
DeepSeek + Gemini; frontier rows are T72-cached single-shot. Run {meta.get('date','')},
git {meta.get('git_commit','')}.</p>

<div class="hero">
  <div class="card"><div class="big">{mu_pct.get('docling',0):.0f}%</div>
    <div class="lbl2">model-union (docling)<br>cheap ∪ cheap, single-shot each<br>
    <b>≥ sonnet-4.6 {front['docling']*100:.0f}%</b>, ~10× cheaper</div></div>
  <div class="card"><div class="big">{mu_pct.get('paddle',0):.0f}%</div>
    <div class="lbl2">model-union (paddle)<br>= sonnet-4.6 {front['paddle']*100:.0f}%</div></div>
  <div class="card"><div class="big" style="color:#1a1a1a">+€{meta.get('run_spend_eur',0):.2f}</div>
    <div class="lbl2">total T74 spend<br>arms A &amp; E &amp; G derived at €0</div></div>
</div>

<div class="verdict"><b>Verdict.</b> "Cheap + loop ≥ expensive + single-shot" holds — but
the winning move is <b>model-union of two cheap models</b> (deepseek-flash ∪ gemini-lite,
one shot each → docling 100%, paddle 95% = frontier), because they miss <i>different</i>
values (decorrelated errors). Within-model passes are weaker: modest (union-k3), two-faced
(requery), or unhelpful (reason-first). <b>parser-union</b> is the reliable closer for the
figure-only coverage gap.</div>

<h2>Reachable-recall by arm (cheap tier)</h2>
<p class="sub">Reachable-recall = recall ÷ parser coverage ceiling (isolates model skill
from parser limits). Each arm targets one T72 miss quadrant.</p>
<table><thead><tr><th>parser</th><th>model</th>{arm_cols}</tr></thead>
<tbody>{grid_rows}</tbody></table>

<h2>Reason-first retest: was the collapse just truncation?</h2>
<p>deepseek-flash on docling — {rf_line}. Raising the output cap recovered most of the
catastrophe (the reasoning field had been truncating the items JSON), but reason-then-format
<b>still underperforms plain extraction</b>. CRANE's reason-before-format does not transfer
to cheap <i>extraction</i> models; gemini-lite was unaffected (92% throughout).</p>

<h2>Gold-thinness: precision was understated</h2>
<p>Of {len(gold)} distinct false-positive groups, by cross-model agreement:
<b>{len(real)} are likely REAL</b> (≥3 independent models extract a value the gold lacks)
vs <b>{len(halluc)} likely hallucinations</b> (1 model only). The "real" FPs are dominated
by measurement <i>types the gold never scoped</i> — so a chunk of the apparent precision
gap is gold-thinness, not model error.</p>
<table><thead><tr><th>candidate type</th><th>value</th><th>paper</th><th>#models agree</th></tr></thead>
<tbody>{gold_rows}</tbody></table>

<div class="note"><b>Honest caveats.</b> Recall is the trustworthy axis; union/parser-union
precision is a lower bound (exact-vs-tolerant dedup + gold-thinness). reason-first-16k spent
~€0.15; all other new arms (model-union, parser-union, gold-thinness) are €0 post-hoc over
cached cells. Frontier is T72-cached single-shot — no frontier multi-pass arm (out of the
DeepSeek+Gemini spend fence).</div>

<p class="foot">Generated by <code>reports/build_t74_report.py</code> from
<code>experiments/results/{{reachable,gold_thinness}}.json</code> +
<code>llm_matrix_t74.csv</code>. See <code>experiments/results/FINDINGS.md</code> Finding #5.</p>
</body></html>"""


def main() -> None:
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
