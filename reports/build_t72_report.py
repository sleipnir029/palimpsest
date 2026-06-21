#!/usr/bin/env python3
"""Build the self-contained T72 benchmark report.

Reads the authoritative 06-21 corrected snapshots + coverage/rescore/meta JSON
from experiments/results/ and bakes everything into one static HTML file
(reports/t72_report.html) with the data inlined as a `const DATA = {...}` block.
No runtime dependencies: charts are hand-built inline SVG + vanilla JS.

Regenerate:  pixi run python reports/build_t72_report.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"
MANIFEST = ROOT / "experiments" / "corpus_manifest.csv"
OUT = Path(__file__).resolve().parent / "t72_report.html"

DATE = "2026-06-21"
PARSERS = ["mineru", "docling", "dots", "paddle"]
# Canonical model roster present in every 06-21 parser grid (gemini-free ran on a
# subset only and is excluded from the comparable grid).
CANON = [
    "openai-frontier",
    "openai-mini",
    "gemini-lite",
    "haiku-4.5",
    "sonnet-4.6",
    "deepseek-flash",
    "deepseek-pro",
]

# Human-facing model metadata (architecture facts used by the "why" section).
MODEL_META = {
    "openai-frontier": dict(name="GPT-5.4", provider="OpenAI", family="GPT",
                            access="closed", tier="frontier", strict=True),
    "openai-mini":     dict(name="GPT-5.4-mini", provider="OpenAI", family="GPT",
                            access="closed", tier="small", strict=True),
    "gemini-lite":     dict(name="Gemini 3.1 Flash-Lite", provider="Google", family="Gemini",
                            access="closed", tier="cheap", strict=True),
    "haiku-4.5":       dict(name="Claude Haiku 4.5", provider="Anthropic", family="Claude",
                            access="closed", tier="small", strict=False),
    "sonnet-4.6":      dict(name="Claude Sonnet 4.6", provider="Anthropic", family="Claude",
                            access="closed", tier="mid", strict=False),
    "deepseek-flash":  dict(name="DeepSeek V4-flash", provider="DeepSeek", family="DeepSeek-MoE",
                            access="open weights", tier="cheap", strict=False),
    "deepseek-pro":    dict(name="DeepSeek V4-pro", provider="DeepSeek", family="DeepSeek-MoE",
                            access="open weights", tier="big", strict=False),
}


def _f(x: str):
    x = (x or "").strip()
    return float(x) if x not in ("", None) else None


def load_grid():
    """rows[parser] = list of dict rows (typed)."""
    rows = {}
    for parser in PARSERS:
        path = RESULTS / f"llm_matrix_{parser}_{DATE}.csv"
        with path.open(newline="") as fh:
            rd = csv.DictReader(fh)
            out = []
            for r in rd:
                out.append(dict(
                    sha8=r["paper_sha8"], parser=r["parser"], label=r["label"],
                    model_id=r["model_id"], role=r["role"], mode=r["mode"],
                    tp=int(r["tp"]), gt=int(r["gt_total"]),
                    recall=_f(r["recall"]), precision=_f(r["precision"]), f1=_f(r["f1"]),
                    eur_paper=_f(r["eur_per_paper"]), eur_tp=_f(r["eur_per_tp"]),
                    latency=_f(r["latency_s"]),
                ))
            rows[parser] = out
    return rows


def cell_agg(rows):
    """Aggregate a list of per-paper rows (one model, one parser, one mode)."""
    tp = sum(r["tp"] for r in rows)
    gt = sum(r["gt"] for r in rows)
    eur = sum(r["eur_paper"] for r in rows if r["eur_paper"] is not None)
    return dict(
        muF1=round(mean(r["f1"] for r in rows), 4),
        muRecall=round(mean(r["recall"] for r in rows), 4),
        muPrecision=round(mean(r["precision"] for r in rows), 4),
        microRecall=round(tp / gt, 4) if gt else None,
        eurPerTp=round(eur / tp, 5) if tp else None,
        eurPerPaper=round(eur / len(rows), 5),
        latency=round(mean(r["latency"] for r in rows), 2),
        papersN=len(rows),
    )


def build_grid(rows):
    """grid[mode][parser][model] = agg ; avgByModel[mode][model] = agg across parsers."""
    grid = {"raw": {}, "strict": {}}
    for mode in ("raw", "strict"):
        for parser in PARSERS:
            grid[mode][parser] = {}
            for model in CANON:
                sub = [r for r in rows[parser]
                       if r["label"] == model and r["mode"] == mode]
                if sub:
                    grid[mode][parser][model] = cell_agg(sub)
    # average across the 4 parsers (only models present in all parsers for that mode)
    avg = {"raw": {}, "strict": {}}
    for mode in ("raw", "strict"):
        for model in CANON:
            present = [grid[mode][p][model] for p in PARSERS if model in grid[mode][p]]
            if len(present) == len(PARSERS):
                avg[mode][model] = dict(
                    muF1=round(mean(c["muF1"] for c in present), 4),
                    microRecall=round(mean(c["microRecall"] for c in present), 4),
                    muPrecision=round(mean(c["muPrecision"] for c in present), 4),
                    eurPerTp=round(mean(c["eurPerTp"] for c in present), 5),
                    eurPerPaper=round(mean(c["eurPerPaper"] for c in present), 5),
                    latency=round(mean(c["latency"] for c in present), 2),
                )
    return grid, avg


def load_coverage():
    cov = json.load((RESULTS / "coverage.json").open())
    out = {}
    figure_only = {}  # value -> set of parsers missing it (paper bd9811a5)
    per_parser_tuples = {}
    for parser in PARSERS:
        covered = total = 0
        per_paper = {}
        for full_sha, rec in cov[parser].items():
            sha8 = full_sha[:8]
            covered += rec["covered"]
            total += rec["total"]
            per_paper[sha8] = dict(covered=rec["covered"], total=rec["total"],
                                   ceiling=round(rec["ceiling"], 4))
            for t in rec["tuples"]:
                if not t["present"]:
                    figure_only.setdefault((t["type"], t["value"], sha8), set()).add(parser)
        out[parser] = dict(covered=covered, total=total,
                            ceiling=round(covered / total, 4), perPaper=per_paper)
    fo = [dict(type=k[0], value=k[1], sha8=k[2], missingFrom=sorted(v))
          for k, v in sorted(figure_only.items(), key=lambda kv: kv[0][1])]
    return out, fo


def load_taxonomy():
    rs = json.load((RESULTS / "rescore.json").open())
    keys = ("hit", "model_gap", "coverage_gap", "wrong_type", "fp")
    per_parser = {p: {k: 0 for k in keys} | {"slots": 0} for p in PARSERS}
    total = {k: 0 for k in keys} | {"slots": 0}
    for c in rs["cells"]:
        if c["mode"] != "raw" or c["label"] not in CANON:
            continue
        p = c["parser"]
        for k in keys:
            per_parser[p][k] += c[k]
            total[k] += c[k]
        per_parser[p]["slots"] += c["gt_total"]
        total["slots"] += c["gt_total"]
    return per_parser, total


def load_papers():
    papers = []
    with MANIFEST.open(newline="") as fh:
        for r in csv.DictReader(fh):
            papers.append(dict(sha8=r["sha256"][:8], doi=r["doi"],
                               filename=r["filename"], n_pages=int(r["n_pages"])))
    return papers


def main():
    rows = load_grid()
    grid, avg = build_grid(rows)
    coverage, figure_only = load_coverage()
    taxonomy, tax_total = load_taxonomy()
    papers = load_papers()

    # gold count per paper (from raw deepseek-pro rows, any parser has full gt)
    gold = {}
    for r in rows["docling"]:
        if r["label"] == "deepseek-pro" and r["mode"] == "raw":
            gold[r["sha8"]] = r["gt"]
    for p in papers:
        p["gold"] = gold.get(p["sha8"])

    # order models by avg raw µF1 (descending) for display
    order = sorted(CANON, key=lambda m: avg["raw"][m]["muF1"], reverse=True)
    palette = ["#0F6E63", "#38618C", "#B07D2B", "#6D4C7D", "#5E8C6A", "#9A6A8C", "#4A4F54"]
    models = []
    for i, m in enumerate(order):
        meta = MODEL_META[m]
        models.append(dict(key=m, color=palette[i % len(palette)], **meta))

    # hero: deepseek-flash rescue across parsers (corrected µF1 + microRecall)
    hero = dict(model="deepseek-flash",
                muF1={p: grid["raw"][p]["deepseek-flash"]["muF1"] for p in PARSERS},
                microRecall={p: grid["raw"][p]["deepseek-flash"]["microRecall"] for p in PARSERS})

    data = dict(
        date=DATE, parsers=PARSERS,
        parserMeta={
            "mineru":  dict(label="MinerU",  figureAware=False, blurb="coarse text blocks"),
            "docling": dict(label="Docling", figureAware=True,  blurb="fine, figure-aware spans"),
            "dots":    dict(label="dots.ocr", figureAware=True,  blurb="OCR, figure-aware"),
            "paddle":  dict(label="PaddleOCR", figureAware=True, blurb="OCR, figure-aware"),
        },
        models=models, papers=papers,
        grid=grid, avgByModel=avg,
        coverage=coverage, figureOnly=figure_only,
        taxonomy=taxonomy, taxonomyTotal=tax_total,
        hero=hero,
    )

    # ---- facts injected into prose (kept exact / single-sourced) ----
    f = {}
    f["DATE"] = DATE
    f["PROMPT_HASH"] = "9f23e7c683a0"
    f["N_MODELS"] = len(CANON)
    f["N_PARSERS"] = len(PARSERS)
    f["N_PAPERS"] = len(papers)
    f["N_GOLD"] = sum(p["gold"] for p in papers)
    f["TOP_MODEL"] = MODEL_META[order[0]]["name"]
    f["TOP_F1"] = f'{avg["raw"][order[0]]["muF1"]:.2f}'
    f["TOP_KEY"] = order[0]
    f["DSPRO_F1"] = f'{avg["raw"]["deepseek-pro"]["muF1"]:.2f}'
    f["DSFLASH_AVG_F1"] = f'{avg["raw"]["deepseek-flash"]["muF1"]:.2f}'
    f["DSFLASH_MINERU"] = f'{grid["raw"]["mineru"]["deepseek-flash"]["muF1"]:.2f}'
    f["DSFLASH_DOCLING"] = f'{grid["raw"]["docling"]["deepseek-flash"]["muF1"]:.2f}'
    f["DSFLASH_MINERU_MR"] = f'{grid["raw"]["mineru"]["deepseek-flash"]["microRecall"]:.2f}'
    f["DSFLASH_DOCLING_MR"] = f'{grid["raw"]["docling"]["deepseek-flash"]["microRecall"]:.2f}'
    f["DSFLASH_EURTP"] = f'{avg["raw"]["deepseek-flash"]["eurPerTp"]*100:.3f}'  # cents
    f["SONNET_EURTP"] = f'{avg["raw"]["sonnet-4.6"]["eurPerTp"]*100:.2f}'
    f["GEMINI_EURTP"] = f'{avg["raw"]["gemini-lite"]["eurPerTp"]*100:.3f}'
    _tps = [avg["raw"][m]["eurPerTp"] for m in CANON]
    f["COST_SPREAD"] = f'{max(_tps)/min(_tps):.0f}'
    f["TAX_SLOTS"] = tax_total["slots"]
    f["TAX_HIT"] = tax_total["hit"]
    f["TAX_HIT_PCT"] = f'{100*tax_total["hit"]/tax_total["slots"]:.0f}'
    f["TAX_MODELGAP"] = tax_total["model_gap"]
    f["TAX_COVGAP"] = tax_total["coverage_gap"]
    f["TAX_WRONGTYPE"] = tax_total["wrong_type"]
    f["TAX_FP"] = tax_total["fp"]
    miss = tax_total["model_gap"] + tax_total["coverage_gap"] + tax_total["wrong_type"]
    f["TAX_MISS"] = miss
    f["TAX_COVGAP_PCT"] = f'{100*tax_total["coverage_gap"]/miss:.0f}'
    f["TAX_MODELGAP_PCT"] = f'{100*tax_total["model_gap"]/miss:.0f}'
    f["CEIL_DOCLING"] = f'{100*coverage["docling"]["ceiling"]:.0f}'
    f["CEIL_PADDLE"] = f'{100*coverage["paddle"]["ceiling"]:.0f}'
    f["CEIL_MINERU"] = f'{100*coverage["mineru"]["ceiling"]:.0f}'
    f["CEIL_DOTS"] = f'{100*coverage["dots"]["ceiling"]:.0f}'
    f["N_FIGONLY"] = len(figure_only)

    if "--dump" in sys.argv:
        print(json.dumps(dict(facts=f, avg=avg["raw"], hero=hero,
                              coverage={p: coverage[p]["ceiling"] for p in PARSERS},
                              taxTotal=tax_total,
                              order=order,
                              figureOnly=figure_only), indent=2))
        return

    html = render(data, f)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  ({len(html):,} bytes)")


def _corpus_rows(data):
    out = []
    for i, p in enumerate(data["papers"], 1):
        ceil = {pa: data["coverage"][pa]["perPaper"].get(p["sha8"], {}).get("ceiling")
                for pa in data["parsers"]}
        note = ""
        if any(c is not None and c < 1 for c in ceil.values()):
            note = ' <span class="flag">figure-only values</span>'
        out.append(
            f'<tr><td class="num">{i}</td>'
            f'<td class="mono">{p["sha8"]}</td>'
            f'<td><a href="https://doi.org/{p["doi"]}">{p["doi"]}</a>{note}</td>'
            f'<td class="num">{p["n_pages"]}</td>'
            f'<td class="num">{p["gold"]}</td></tr>'
        )
    return "\n".join(out)


def _roster_rows(data):
    out = []
    for m in data["models"]:
        dot = f'<span class="swatch" style="background:{m["color"]}"></span>'
        access = ("open" if "open" in m["access"] else "closed")
        out.append(
            f'<tr><td>{dot}<span class="mono">{m["key"]}</span></td>'
            f'<td>{m["name"]}</td><td>{m["provider"]}</td>'
            f'<td>{m["family"]}</td>'
            f'<td><span class="tag tag-{access}">{m["access"]}</span></td>'
            f'<td>{m["tier"]}</td></tr>'
        )
    return "\n".join(out)


def _figureonly_list(data):
    items = []
    for t in data["figureOnly"]:
        miss = ", ".join(data["parserMeta"][p]["label"] for p in t["missingFrom"])
        items.append(f'<li><span class="mono">{t["value"]:g} mV/dec</span> '
                     f'<span class="muted">({t["type"]}, paper {t["sha8"]})</span> '
                     f'&mdash; absent from {miss}</li>')
    return "\n".join(items)


OBJECTIONS = [
    ("&ldquo;deepseek-flash is just a bad model.&rdquo;",
     "Artifact, not defect.",
     "The same weights score &micro;F1 <span class='mono'>%%DSFLASH_MINERU%%</span> on MinerU and "
     "<span class='mono'>%%DSFLASH_DOCLING%%</span> on Docling. The collapse tracks the parser&rsquo;s "
     "granularity and coverage, not the model&rsquo;s capability. A defect would not heal when you swap the reader."),
    ("&ldquo;Your best models still miss ~18%. That&rsquo;s the model&rsquo;s ceiling.&rdquo;",
     "Mostly a parser ceiling, not the model.",
     "Of <span class='mono'>%%TAX_MISS%%</span> misses across the grid, <span class='mono'>%%TAX_COVGAP%%</span> "
     "(%%TAX_COVGAP_PCT%%%) are <em>coverage gaps</em> &mdash; the value is physically absent from the parser&rsquo;s "
     "text. Only <span class='mono'>%%TAX_MODELGAP%%</span> are genuine model gaps. No model can extract what the "
     "parser never emitted."),
    ("&ldquo;How do I trust your gold standard?&rdquo;",
     "It was independently re-read by hand.",
     "Every one of the original 41 numbers was checked against the source PDF. All were real; one was a "
     "<em>mislabel</em> (a measurement-window note read as a durability test) and was struck. That single "
     "correction removed 24 spurious model-gaps from the grid."),
    ("&ldquo;Precision looks low &mdash; the models hallucinate.&rdquo;",
     "Precision is structurally understated.",
     "On the thin-gold papers, models extract real, in-scope values the gold simply omits; the scorer counts "
     "those as false positives. The <span class='mono'>%%TAX_FP%%</span> FP count is therefore an <em>upper "
     "bound</em> on hallucination, not a measurement of it."),
    ("&ldquo;Did forcing a JSON schema help?&rdquo;",
     "It net-hurt the cheap models.",
     "Constrained (&lsquo;strict&rsquo;) decoding dropped Gemini Flash-Lite&rsquo;s F1 sharply on several cells "
     "and barely moved the GPTs. The production-faithful &lsquo;raw&rsquo; mode is the headline; strict is shown "
     "for contrast. (See &sect;5: format restriction degrades reasoning.)"),
    ("&ldquo;Why a deterministic scorer instead of an LLM judge?&rdquo;",
     "Reproducibility.",
     "Grading LLM output with an LLM is circular, costs money, and injects the judge&rsquo;s own variance into "
     "the thing being measured. A &plusmn;1% tolerance check is free, auditable, and identical on every re-run."),
    ("&ldquo;Are individual cells stable run-to-run?&rdquo;",
     "Structure yes, single cells no.",
     "Only DeepSeek is pinned to temperature 0; other cells move &plusmn;a few points. So the page reports "
     "<em>worst-case across parsers</em> as the robustness metric, not a single peak cell, and every paid call "
     "is cached so a re-score is deterministic."),
    ("&ldquo;Right number, wrong catalyst?&rdquo;",
     "Acknowledged scope limit.",
     "A bare (type, value) tuple is meaning-blind: a &lsquo;40&nbsp;h&rsquo; stability can belong to a "
     "<em>reference</em> catalyst, not the hero material. Fixing this needs catalyst + condition in the gold and "
     "a meaning-aware scorer &mdash; deliberately deferred, and flagged rather than hidden."),
    ("&ldquo;Then why is the locked runtime default still the weakest overall model?&rdquo;",
     "An open decision, surfaced honestly.",
     "deepseek-flash is the cheapest by far but the lowest average. The candidates are deepseek-pro (a same-provider, "
     "same-wire drop-in that never collapses) or gemini-3.1-flash-lite (best average, but a new provider). It is a "
     "config-locked call &mdash; see &sect;8."),
]


def _objection_blocks():
    out = []
    for i, (q, verdict, body) in enumerate(OBJECTIONS, 1):
        out.append(
            f'<div class="obj">'
            f'<div class="obj-q"><span class="obj-n">{i:02d}</span>{q}</div>'
            f'<div class="obj-a"><span class="obj-v">{verdict}</span> {body}</div>'
            f'</div>'
        )
    return "\n".join(out)


SOURCES = [
    ("Liu et&nbsp;al. 2023", "Lost in the Middle: How Language Models Use Long Contexts",
     "arXiv:2307.03172", "https://arxiv.org/abs/2307.03172",
     "U-shaped accuracy: facts in the middle of a context are recalled far worse than at the edges."),
    ("Su et&nbsp;al. 2021", "RoFormer: Enhanced Transformer with Rotary Position Embedding",
     "arXiv:2104.09864", "https://arxiv.org/abs/2104.09864",
     "RoPE &mdash; the positional scheme whose long-term decay biases attention toward span edges."),
    ("DeepSeek-AI 2024", "DeepSeek-V3 Technical Report",
     "arXiv:2412.19437", "https://arxiv.org/abs/2412.19437",
     "Mixture-of-Experts with Multi-head Latent Attention: 671B params, ~37B active per token."),
    ("Tam et&nbsp;al. 2024", "Let Me Speak Freely? On the Impact of Format Restrictions on LLM Performance",
     "arXiv:2408.02442", "https://arxiv.org/abs/2408.02442",
     "Tighter format constraints (JSON-schema decoding) measurably degrade reasoning, more so for weaker models."),
    ("Singh &amp; Strouse 2024", "Tokenization counts: the impact of tokenization on arithmetic in frontier LLMs",
     "arXiv:2402.14903", "https://arxiv.org/abs/2402.14903",
     "How a tokenizer splits digits changes numeric fidelity &mdash; the mechanism behind value drift."),
]


def _sources_list():
    out = []
    for who, title, ref, url, gloss in SOURCES:
        out.append(
            f'<li><span class="src-who">{who}</span> '
            f'<a href="{url}">{title}</a> '
            f'<span class="mono muted">{ref}</span>'
            f'<div class="src-gloss">{gloss}</div></li>'
        )
    return "\n".join(out)


def render(data, f):
    data_json = json.dumps(data, separators=(",", ":"))
    html = TEMPLATE
    html = html.replace("%%DATA_JSON%%", data_json)
    html = html.replace("%%CORPUS_ROWS%%", _corpus_rows(data))
    html = html.replace("%%ROSTER_ROWS%%", _roster_rows(data))
    html = html.replace("%%FIGUREONLY%%", _figureonly_list(data))
    html = html.replace("%%OBJECTIONS%%", _objection_blocks())
    html = html.replace("%%SOURCES%%", _sources_list())
    for k, v in f.items():
        html = html.replace(f"%%{k}%%", str(v))
    return html


# Loaded last so the long template string lives at the bottom of the file.
from _t72_template import TEMPLATE  # noqa: E402


if __name__ == "__main__":
    main()
