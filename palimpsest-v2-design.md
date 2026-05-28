# Palimpsest v2 — Design & Implementation Plan

**Project:** palimpsest — structured data extraction from PEM electrolyzer / OER catalyst literature
**Author / student:** Rahat (MSc Computational Materials Engineering, RWTH Aachen)
**Scope:** 10-credit mini-thesis, ~400 LOC custom agent, 25+ paper corpus
**Stack constraints:** No agent frameworks, no MCP servers, no LLM gateways. Plain Python 3.11.
**Budget:** €50 hard cap for the running agent (LLM + cloud GPU). Claude Code subscription (used to *build* palimpsest) is separate.

---

## 1. North Star (read every session)

Build the smallest possible agent that turns a folder of PEM electrolyzer / OER catalyst PDFs into a queryable, provenance-tracked, ontology-aligned RDF knowledge graph, with an honest head-to-head comparison of four state-of-the-art parsers as a thesis contribution.

**Five rules that override everything else:**

1. **Plain Python, no frameworks.** ~400 LOC modeled on Thorsten Ball's "How to Build an Agent" loop. No LangChain, LangGraph, CrewAI, AutoGen, smolagents, pydantic-ai. No MCP. No LiteLLM / OpenRouter.
2. **Parse once, cache forever.** Each PDF is parsed by each parser exactly once — the corpus runs one parser-pod at a time (the four parsers ship as isolated images) — outputs are stored by SHA-256 content hash in SQLite, and every subsequent need for that paper reads from cache.
3. **Provenance is non-negotiable.** Every extracted triple carries `(paper_hash, parser_name, page, bbox, run_id)`. The viewer must let Rahat click any value and see the exact glyph it came from.
4. **Schema-first, then extraction.** LinkML schema generates Pydantic, JSON-Schema, JSON-LD context, and SHACL shapes. Every slot has an explicit `slot_uri` — EMMO ECHO when possible, palimpsest-local with `skos:closeMatch` when not.
5. **€50 is a hard wall.** CostMeter refuses to dial any API once spend hits €50. The `/budget` slash command can raise it live, but the default is €50.

If a session ends with the agent doing something other than (a) building one of the 14 components below, (b) running an experiment, or (c) documenting a finding for the thesis defence — it was a wasted session.

---

## 2. TL;DR

- **Architecture:** ~400 LOC Python agent loop (direct Anthropic SDK), prompt-cached Claude Sonnet 4.5 as the primary brain, LinkML→Pydantic+SHACL schema, pyoxigraph (RocksDB) for the triple store, FastAPI + vendored PDF.js + HTMX for the bbox-hover viewer, Textual chat TUI, dulwich for git-style versioning of the graph, marimo notebooks spawned on demand.
- **Parser strategy (thesis contribution):** All four heavyweight parsers — **docling (via `ibm-granite/granite-docling-258M`, released Sept 2025), MinerU 2.5 (1.2B VLM, 75.2 on olmOCR-Bench), olmOCR 2 (checkpoint `olmOCR-2-7B-1025`, 7B VLM, RLVR-trained), and Chandra (v0.1.0 9B at 83.1 ± 0.9%, or Chandra 2 4B at 85.9% — current SOTA)** — each run in its own isolated image on a RunPod RTX 4090 ($0.34/hr community cloud, $0.69/hr secure cloud, verified April 2026), with outputs cached side-by-side in SQLite by content hash. Local CPU keeps `pymupdf4llm` + GROBID for cheap text/bibliographic lookups only; they are **not** part of the comparison.
- **Budget reality:** 25 papers × 4 parsers ≈ 1–2 GPU-hours ≈ €0.30–0.70 in GPU. Sonnet 4.5 extraction with 1-hour prompt caching (cache write 2× base = $6/MTok, cache read 0.1× base = $0.30/MTok) ≈ €8–25 across the project. **€50 hard cap is comfortable; spend is dominated by re-runs and exploration, not parsing.**

---

## 3. Key Findings (the 14 components)

### F1. LLM selection — Claude Sonnet 4.5 with prompt caching, three explicit fallbacks
**Verdict:** Sonnet 4.5 is the right default. Use prompt caching aggressively.

- Sonnet 4.5 API pricing (Anthropic official pricing page, `platform.claude.com/docs/en/about-claude/pricing`): **$3.00 / MTok input, $15.00 / MTok output**, 200K context. **5-min cache writes 1.25× input = $3.75/MTok; 1-hour cache writes 2× input = $6/MTok**; cache reads 0.1× input = **$0.30/MTok**. Minimum cache checkpoint for Sonnet 4.5 is **4,096 tokens**, easily met by a ~12K-token system+schema+skill prefix.
- The 1-hour TTL is the right choice for palimpsest's bursty extraction sessions; the 5-min TTL is fine for a tight inner loop.
- Slash-command fallbacks (`/model haiku`, `/model deepseek`, `/model gemini`) call Haiku 4.5 ($1/$5), DeepSeek V3.2, and Gemini 2.5 Flash via their respective native SDKs. **No gateway.** Each is a `Provider` subclass with `.complete(messages, tools)` returning a normalized response — ~80 LOC each.

### F2. Agent loop — Thorsten Ball pattern, ~80 LOC
**Verdict:** The canonical loop from `ampcode.com/notes/how-to-build-an-agent` is sufficient. Resist all temptation to add a planner / critic / router / etc.

```python
def run(agent):
    while True:
        user_msg = ui.read_input()
        if user_msg.startswith("/"): slash_dispatch(user_msg); continue
        agent.messages.append({"role": "user", "content": user_msg})
        while True:
            resp = provider.complete(
                system=agent.system_prompt,           # cache breakpoint 1
                tools=agent.tools,                    # cache breakpoint 2
                messages=agent.messages,
                cache_control_on=("system", "tools"),
            )
            agent.messages.append({"role": "assistant", "content": resp.content})
            cost_meter.record(resp.usage)
            tool_calls = [b for b in resp.content if b.type == "tool_use"]
            if not tool_calls: break
            results = [agent.tools[c.name].run(**c.input) for c in tool_calls]
            agent.messages.append({"role": "user", "content": results})
```

That is the entire heartbeat. Everything else is tools + UI + storage.

### F3. Agent Skills — filesystem-based, Anthropic's December 2025 convention
**Verdict:** Ship one skill in MVP (`oer-extraction`); keep the loader trivial so HER / CO2RR / NRR can be added later by dropping a folder.

- Anthropic's Agent Skills spec (announced Dec 18 2025 at `anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills`; open standard at `agentskills.io`): a skill is a folder containing a `SKILL.md` with YAML frontmatter (`name`, `description`) and instructions. Progressive disclosure: only the frontmatter is in the system prompt at startup; the body is loaded by the agent on demand.
- Implementation: `skills/oer-extraction/SKILL.md` describes what an OER extraction looks like (which slots, which heuristics, which units, which traps — e.g. iR-correction, scan-rate sensitivity, Tafel-from-LSV pitfalls). A `read_skill(name)` tool pulls the full body into context when picked.
- Adding HER later is literally `skills/her-extraction/SKILL.md` — no loop changes.

### F4. Parser orchestration — all four on cloud GPU, one isolated image per parser
**Verdict:** Promote docling to a first-class remote parser. Eliminate the docling-on-M1 dependency hell. RTX 4090 (24 GB VRAM) is enough for any one of the four.

VRAM footprints (verified):

- **docling** — runs the docling-ibm-models pipeline (layout + TableFormer) on RTX. As of Sept 2025 IBM ships `ibm-granite/granite-docling-258M` served via vLLM: `vllm serve ibm-granite/granite-docling-258M`, with recommended `page_batch_size = 64` for RTX 4090 (per the official RTX-acceleration docs at `docling-project.github.io/docling/getting_started/rtx/`). VRAM utilization ~90% with `--gpu-memory-utilization 0.9`.
- **MinerU 2.5** — 1.2B decoupled VLM (`opendatalab/MinerU2.5-2509-1.2B`, arXiv 2509.22186, Sept 30 2025), fits comfortably in 24 GB. Overall olmOCR-Bench score **75.2** (leading in arXiv Math 76.6, Old Scans Math 54.6, Long Tiny Text 83.5).
- **olmOCR 2** — checkpoint **`olmOCR-2-7B-1025`**, ~7B-param VLM trained with reinforcement learning with verifiable rewards (RLVR), per Poznanski, Soldaini & Lo, arXiv 2510.19817 (22 Oct 2025). FP16 fits in ~14 GB on RTX 4090.
- **Chandra OCR** — two model lines: **Chandra v0.1.0 is a 9B-param model scoring 83.1 ± 0.9% on olmOCR-Bench** (release Oct 26 2024, per Datalab); **Chandra OCR 2 is a separate 4B model released March 18 2026 scoring 85.9%** — current state of the art, smaller and more accurate than Chandra 1 across every category (per `datalab-to/chandra` GitHub releases). 8–12 GB VRAM recommended. **Default to Chandra 2 for the thesis comparison; cite v0.1.0 results as the historical baseline.**

Each parser therefore runs comfortably on a single RTX 4090 — one parser per pod, so the four
24 GB-tight VLMs never have to co-reside. We target **RunPod community cloud** (≈$0.34/hr for a 4090, ≈$0.69/hr secure as fallback when community is unavailable — April 2026 reference points; the CostMeter bills each pod's actual rate read from the RunPod API).

**Local CPU parsers are explicitly out of the comparison.** `pymupdf4llm` and a Dockerised GROBID exist for cheap quick lookups (abstract, references, author list) but are never benchmarked against the four heavy parsers — they live on M1 and never see RunPod.

### F5. Parse-once cache — SQLite table keyed by SHA-256
**Verdict:** This is the single most important budget lever. See Appendix C for DDL.

When the agent encounters a new PDF, it computes `sha256(pdf_bytes)`; the batch runner sends it through each parser's pod in turn, writes a blob file per parser to `cache/{hash}/{parser}.json|md`, and inserts one row per parser into the `parser_runs` table. Every subsequent need for that paper checks the table and reads from disk. **Re-extracting a paper never re-parses.**

### F6. Env management — pixi, Python 3.11
**Verdict:** `pixi` (not bare conda, not poetry, not uv-alone) because pixi handles the conda-forge binaries (pyoxigraph, dulwich) on macOS arm64 cleanly while still managing pip-only packages.

- `pixi.toml` pins Python 3.11, `pyoxigraph >= 0.5.8`, anthropic SDK, marimo, textual, rich, typer, fastapi, linkml, pyshacl, rdflib, dulwich, httpx, pymupdf4llm.
- Cloud GPU side runs **four isolated Docker images, one per parser** — `palimpsest/docling`, `palimpsest/mineru`, `palimpsest/chandra` (we build these; weights pre-pulled), plus Allen AI's **upstream** olmOCR image used as-is. They are kept separate because the parsers' `torch`/`vLLM`/`transformers` pins conflict; stacking them in one image risks an unsatisfiable resolver or silent version clobbering that would corrupt the parser comparison.
- M1 Air is the primary dev box; everything except parsing runs locally.

### F7. Ontology layer — EMMO ECHO + QUDT + PROV-O + palimpsest-local
**Verdict:** EMMO Domain Electrochemistry covers more than expected, but **two key OER concepts (Oxygen Evolution Reaction itself, and Tafel slope/equation) are missing**. Mint palimpsest-local IRIs for those with `skos:closeMatch` to the nearest EMMO term. See Appendix E for the full per-slot table.

Verified EMMO ECHO IRIs (from the published class index at `emmo-repo.github.io/domain-electrochemistry/electrochemistry.html` and the JSON-LD context at `w3id.org/emmo/domain/electrochemistry/context`):

| EMMO concept | Verified IRI hash |
|---|---|
| Overpotential | `electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6` |
| ActivationOverpotential | `electrochemistry_7fa406b0_512a_4d59_9e0c_5d8aba0103ae` |
| AnodicOverpotential | `electrochemistry_565c0b10_70fe_441a_b76a_b9a8e08ca7b7` |
| CathodicOverpotential | `electrochemistry_0853b072_3b80_4864_8147_24ce35407ade` |
| Electrocatalyst | `electrochemistry_a3b53904_22b1_42a9_a515_c8a3aed7e841` |
| ChargeTransferCoefficient | `electrochemistry_a4dfa5c1_55a9_4285_b71d_90cf6613ca31` |
| ButlerVolmerEquation | `electrochemistry_d48ea516_5cac_4f86_bc88_21b6276c0938` |
| AnodicReaction | `electrochemistry_a0580fa9_5073_44af_b33e_7adbc83892d0` |
| ElectrodeReaction | `electrochemistry_2e3e14f9_4cb8_45b2_908e_47eec893dec8` |

**Confirmed missing from EMMO ECHO (must be palimpsest-local with `skos:closeMatch`):**
- **OxygenEvolutionReaction** — no `OxygenEvolutionReaction` class. Closest are `OxygenElectrode`, `AnodicReaction`, `GasEvolution`.
- **TafelSlope / TafelEquation** — no `Tafel*` class anywhere in the ontology; the only kinetic-relation class is `ButlerVolmerEquation`.

These become `palimpsest:OxygenEvolutionReaction` and `palimpsest:TafelSlope` under `https://w3id.org/palimpsest/`, with `skos:closeMatch` to `AnodicReaction` and `ButlerVolmerEquation` respectively, plus a `TODO_EMMO_UPSTREAM:` comment in the schema documenting what to request from the EMMO maintainers. **This ontology-gap analysis is itself a thesis contribution.**

Units come from QUDT (`http://qudt.org/vocab/unit/` — verified: `MilliV`, `MilliV-PER-SEC`, `MilliA-PER-CentiM2`, `PER-SEC`, `V`, `PH`). Provenance from PROV-O (`http://www.w3.org/ns/prov#`). Bibliographic from schema.org.

### F8. LinkML schema — generates Pydantic, JSON-Schema, JSON-LD, SHACL
**Verdict:** One source of truth. `gen-pydantic`, `gen-json-schema`, `gen-jsonld-context`, `gen-shacl` are run as a `pixi run schema` task.

Each measurement slot uses LinkML's `unit` block (QUDT IRI), `slot_uri` (EMMO or palimpsest), `exact_mappings` / `close_mappings` (SKOS), and `examples`. Pydantic models are imported by the agent's extraction tool to validate before insertion.

**Exploration mode**: when the user says "I think there's a new field we should track", the agent (a) drafts a new LinkML slot YAML, (b) shows it to the user, (c) appends it to `schema/exploratory.yaml` (not the main schema), and (d) records a dulwich commit. Promoting an exploratory slot to the main schema is a manual review step. This is how palimpsest scales beyond the initial OER vocabulary without silently corrupting the main schema.

### F9. Provenance viewer — FastAPI + vendored PDF.js + HTMX
**Verdict:** Build the minimum: left pane with the rendered PDF (PDF.js), right pane with extracted triples, bbox-hover highlighting. No SPA. HTMX `hx-trigger="mouseover"` flips a CSS class on the PDF overlay div. ~300 LOC of Python + ~150 of templated HTML.

### F10. TUI — chat-first Textual screen, slash commands secondary
**Verdict:** Home screen is a chat box. The user types natural language. Slash commands exist for explicit control but are *not* the primary mode.

```
┌─ palimpsest ──────────────────────────────────────[€12.40/€50]┐
│ > extract the overpotentials at 10 mA/cm² from all five papers│
│ ✓ found 5 cached parses                                       │
│ ✓ matched 5 values (mean 312 ± 41 mV vs RHE)                  │
│ > open the analysis notebook                                  │
│ ✓ marimo edit notebooks/overpotentials.py → :2718             │
│ _                                                             │
└───────────────────────────────────────────────────────────────┘
```

Other screens (cost dashboard, paper queue, skills list, settings) are bound to F-keys and to `/cost`, `/queue`, `/skills`, `/settings`. The agent never forces a screen switch; it reports what it did and stays in chat.

### F11. Marimo notebooks — agent spawns `marimo edit` on request
**Verdict:** When the user asks "open the analysis notebook" or "make me a notebook to compare Tafel slopes", the agent writes a `.py` file under `notebooks/` and spawns `marimo edit notebooks/<name>.py` as a subprocess, then reports the localhost URL.

- Confirmed CLI from marimo docs: `marimo edit notebook.py` is the canonical invocation. Marimo notebooks are pure `.py` files (git-friendly) and the reactive runtime handles cell execution inside the browser UI.
- The agent does **not** auto-execute notebook code beyond what marimo's reactive runtime does on cell change. No headless `marimo run` from the agent.

```python
def open_notebook_tool(name: str, content: str) -> str:
    path = Path("notebooks") / f"{name}.py"
    path.write_text(content)
    proc = subprocess.Popen(["marimo", "edit", str(path),
                             "--headless", "--port", "0"])
    port = wait_for_port(proc, timeout=5)
    return f"http://localhost:{port}"
```

### F12. Versioning — dulwich, git-style commits on every extraction
**Verdict:** `dulwich.porcelain.commit()` after every batch. The `.git` directory lives next to the pyoxigraph store. Every commit message is `extract: {paper_hash} via {parser} ({n} triples)`. Reset is `dulwich.porcelain.reset()` to a known commit. Diff is exposed as `/diff <sha>` in the TUI.

### F13. CLAUDE.md — Karpathy-inspired, under 100 lines, directive
**Verdict:** Drop the previous AGENT.md draft entirely. Use the four Karpathy principles (Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution, as published in `forrestchang/andrej-karpathy-skills` derived from Karpathy's January 2026 X post on LLM coding pitfalls) plus a project-specific anti-feature-creep checklist. See Appendix A.

### F14. Anti-patterns to refuse on sight
1. "Let's add a planner agent" → no. One loop.
2. "Let's use LangGraph for the parser pipeline" → no. A `for parser in PARSERS:` loop.
3. "Let's expose the parsers as MCP servers" → no. Python function calls.
4. "Let's add LiteLLM so we can swap models easier" → no. Three SDK subclasses.
5. "Let's make a web UI" → no, except the provenance viewer (single page, HTMX).
6. "Let's vector-search across papers" → no, unless an experiment explicitly requires it.
7. "Let's add Celery / Redis / Postgres" → no. SQLite + pyoxigraph + dulwich.
8. "Let's run docling locally on M1 too" → no. Docling runs only on RunPod.

---

## 4. Details (for the thesis defence)

### 4.1 Parser comparison as a thesis contribution
The four parsers represent four different design philosophies as of late 2025 / early 2026:

- **docling (IBM)** — traditional layout-detection + TableFormer + OCR pipeline, MIT licensed; recently gained NVIDIA RTX acceleration via the **`granite-docling-258M`** VLM (released Sept 2025) served through vLLM (`vllm serve ibm-granite/granite-docling-258M`).
- **MinerU 2.5 (OpenDataLab)** — decoupled VLM, 1.2B params, score **75.2** on olmOCR-Bench (arXiv 2509.22186), optimized for high-resolution document parsing with low compute.
- **olmOCR 2 (AllenAI)** — checkpoint **`olmOCR-2-7B-1025`**, 7B VLM trained with reinforcement learning with verifiable rewards (RLVR), ships training code (arXiv 2510.19817).
- **Chandra OCR (Datalab)** — two model lines: v0.1.0 (9B, 83.1 ± 0.9%, Oct 2024) and Chandra 2 (4B, 85.9%, Mar 2026) — current SOTA on olmOCR-Bench, strong on tables/forms/handwriting.

**Thesis contribution:** run all four on the same 25+ paper corpus and report:
1. text accuracy on a hand-labeled 5-paper subset,
2. table-cell F1 on key OER tables (Tafel/overpotential/ECSA),
3. bbox precision (do they tell us *where* a number came from?),
4. wall-clock seconds/page on RTX 4090,
5. total cost per paper,
6. **downstream extraction accuracy conditional on parser** (i.e. how well does Sonnet 4.5 do given each parser's output?) — this last one is the most thesis-relevant.

### 4.2 GPU lifecycle and CostMeter
`gpu_provider` is a context manager that calls the RunPod REST API to (a) start a pod from the requested parser's template (one template per parser image), (b) wait for SSH ready, (c) tunnel a port, (d) yield a `RunPodSession` object, (e) on `__exit__`, send a stop signal. The CostMeter wraps connect/disconnect timestamps and bills wall-clock at **the pod's actual hourly rate**, read from the RunPod API pod object (`adjustedCostPerHr` or `costPerHr`) at start — so the charge tracks whatever GPU type and cloud (community/secure/spot) the pod actually got, not a hardcoded number. An **idle watchdog** sends a soft stop at 60 s of no activity; a **hard kill** at 5 minutes idle protects against hangs. See Appendix C.

### 4.3 Budget math (25 papers, RTX 4090 community cloud, Sonnet 4.5 + caching)

**Parsing (one-time, amortized):**
- 25 papers × ~10 pages/paper × 4 parsers
- Empirical assumption: ~1 s/page docling, ~2 s/page MinerU, ~3 s/page olmOCR, ~2 s/page Chandra → ~8 s/page × 250 pages ≈ 33 min of pure parser time.
- Batch-by-parser means **4 pod sessions** (one per isolated image), not one. Each pod's steady-state startup is ~90 s and it loads only its single model (~45 s, vs ~3 min for all four together) → ~9 min of startup/load overhead. (The 10–15 GB image pull is a one-time cold cost per image, then cached host-side by RunPod.) With I/O, ~1–1.5 hours wall-clock per *batch* of 25 papers.
- At ~$0.34/hr (illustrative, RTX 4090 community; the CostMeter bills each pod's *actual* rate read from the RunPod API): **~$0.45 (≈ €0.40) to parse the entire 25-paper corpus once** — isolation costs ~€0.10 more than the old single-pod estimate, a price worth paying for non-conflicting parser envs.
- 5× headroom for re-runs, parser updates, new papers: **€2–4 total parsing cost.**

**Extraction (Sonnet 4.5 with prompt caching, 1-hour TTL):**
- Cached prefix per call ≈ system prompt + schema + skill ≈ ~12K tokens (1-hour cache write once = 12K × $6/MTok = $0.072; reads at $0.30/MTok = $0.0036 each).
- Per-paper extraction: ~3–5 LLM calls × (5K fresh input + 3K output) = 25K fresh input ($0.075) + 15K output ($0.225) + ~50K cache reads ($0.015) ≈ **$0.32 per paper.**
- 25 papers × $0.32 = **$8.00**.
- 3× headroom for iteration, exploratory queries, viewer-driven re-prompting: **$24 ≈ €22.**

**Total expected spend across the entire thesis:** ~€25, leaving ~€25 of headroom under the €50 cap. The `/budget` slash command lets Rahat raise it live if a thesis demo runs hot.

### 4.4 Why no MCP, no gateway, no framework
- **MCP** adds a server process, a JSON-RPC transport, and a discovery layer for tools that we already implement as Python functions. For ~12 tools across one repo, that overhead is pure noise. (If palimpsest ever grows to multiple repos sharing tools, revisit.)
- **LLM gateways** add another vendor, another API key, another billing surface, and remove provider-specific features like Anthropic's `cache_control` block. Three `Provider` subclasses with ~80 LOC each are easier to reason about and let prompt caching work natively.
- **Agent frameworks** impose a control-flow vocabulary (`AgentExecutor`, `Graph`, `Crew`) that is heavier than the ~30-line loop in F2. Thorsten Ball's "an agent is an LLM, a loop, and enough tokens" is the right framing for a thesis-scope project.

---

## 5. Recommendations — execution order

**Week 1 (foundations):**
1. `pixi init`, dependency lock, repo skeleton (Appendix B).
2. Write CLAUDE.md (Appendix A) and commit.
3. Implement the agent loop (F2) with one tool (`read_paper`) and the Anthropic provider only. Verify on a single PDF.
4. Add CostMeter with €50 default cap and SQLite persistence.

**Week 2 (parsing & cache):**
5. Build the four parser images — `docling` / `mineru` / `chandra` (we build, weights pre-pulled) + olmOCR's upstream image — and register one RunPod template per image.
6. Implement `gpu_provider` context manager with RunPod REST API (parser-agnostic; caller passes the parser's template).
7. Implement parser cache (Appendix C). End-to-end: agent receives a PDF, the batch runner sends it through each parser's pod in turn, caches outputs, tears down each pod. Verify SHA-256 hit on second call.

**Week 3 (schema & extraction):**
8. Author the LinkML schema with EMMO / QUDT / palimpsest-local IRIs (Appendix E). Generate Pydantic + SHACL.
9. Write the `oer-extraction` skill (`skills/oer-extraction/SKILL.md`).
10. Implement `extract_to_graph` tool: takes parser output + skill, calls Sonnet 4.5 with `cache_control`, validates against Pydantic, runs SHACL, inserts into pyoxigraph.

**Week 4 (UI & viewer):**
11. Textual chat TUI (F10) with the 10 slash commands (Appendix D).
12. FastAPI + PDF.js + HTMX provenance viewer (F9).
13. Marimo notebook spawn tool (F11).

**Week 5 (thesis experiments):**
14. Run the 4-way parser comparison on the 25-paper corpus. Hand-label a 5-paper subset for accuracy ground truth.
15. SPARQL queries across the graph for the thesis chapter: "overpotential at 10 mA/cm² by catalyst family", "Tafel slope vs electrolyte pH", "ECSA-normalized vs geometric current density", etc.
16. Write up: methodology, parser comparison, ontology gap analysis.

**Stop conditions / benchmarks that change the plan:**
- If by end of Week 2 the GPU pipeline costs more than €5 to parse 5 papers → something is wrong; investigate before continuing.
- If end-to-end extraction accuracy on the 5 hand-labeled papers is < 80% by end of Week 3 → refine the skill, not the loop.
- If the LinkML schema needs more than 30 slots → scope creep; trim.
- If total spend hits €30 before Week 5 → freeze new experiments, finish the thesis.

---

## 6. Caveats

- **RunPod RTX 4090 community-cloud availability varies by region.** If unavailable, fall back to secure cloud ($0.69/hr) — doubles GPU cost but still trivial against €50.
- **EMMO Domain Electrochemistry is still evolving.** The OER and Tafel-slope gaps are real as of May 2026 verification; if EMMO ships those classes during the thesis, swap the palimpsest-local IRIs.
- **Prompt-caching savings depend on prefix stability.** If the system prompt or schema changes mid-session, the cache is invalidated and the next call pays the write cost. Discipline: only edit the system prompt at session boundaries. The `/model` command also invalidates the cache (different provider).
- **Chandra and olmOCR licenses must be re-verified** before any commercial use; for a thesis they are fine, but the comparison chapter should cite the licenses explicitly. **Chandra v0.1.0 vs Chandra 2 are distinct models** — be explicit which version's numbers you cite.
- **The 5 attached Nature OER papers are reference / development data, not the corpus.** Rahat must source 20+ additional PEM electrolyzer / OER catalyst PDFs (open-access preferred) before the thesis defence.
- **`marimo edit` opens a browser by default**; on a headless dev VM use `--headless` and tunnel the port.
- **The "downstream extraction accuracy conditional on parser" experiment is the most novel of the F4 contributions** — but it requires hand-labeled ground truth on the 5 reference papers. Budget time for that explicitly.

---

## Appendix A — CLAUDE.md (paste-ready, 96 lines, Karpathy-inspired)

```markdown
# CLAUDE.md — palimpsest

You are helping Rahat build palimpsest: a small Python agent that extracts
structured data from PEM electrolyzer / OER catalyst PDFs into an
ontology-aligned RDF graph. It is a 10-credit MSc mini-thesis at RWTH.
The whole agent is ~400 lines of Python. Keep it that way.

## 1. Think before coding
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them. Do not pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what is confusing. Ask.

## 2. Simplicity first
- Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that was not requested.
- If you write 200 lines and it could be 50, rewrite it.
- Ask: "would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical changes
- Touch only what you must.
- Do not "improve" adjacent code, comments, or formatting.
- Do not refactor things that are not broken.
- Match existing style, even if you would do it differently.
- Clean up only your own mess.

## 4. Goal-driven execution
- Given a goal and success criteria, loop until verified.
- Run the tests yourself before claiming done.
- If a verification step fails, name the failure and fix it.

## Project rules (override the four above when they conflict)

### Stack — locked
- Python 3.11, pixi. macOS arm64 primary dev.
- Direct Anthropic SDK. Direct DeepSeek / Gemini SDKs for fallback only.
- No agent frameworks (LangChain, LangGraph, CrewAI, AutoGen, smolagents, pydantic-ai).
- No MCP servers. Python function calls only.
- No LLM gateways (LiteLLM, OpenRouter).
- pyoxigraph for RDF. SQLite for cache + CostMeter. dulwich for versioning.
- LinkML for schema. EMMO ECHO + QUDT + PROV-O + palimpsest-local IRIs.
- Textual + Rich + Typer for TUI. FastAPI + vendored PDF.js + HTMX for viewer.
- marimo for notebooks (spawned by the agent, never auto-executed).

### Budget — €50 hard cap
- CostMeter must be checked before every paid API call.
- €40 → warn in TUI. €50 → refuse to call. `/budget N` raises the cap live.
- The Claude Code subscription used to BUILD palimpsest is separate from the
  €50; the €50 is what palimpsest itself spends when it runs.

### Parsers — all four, cloud only
- docling, MinerU, olmOCR, Chandra all run on RunPod RTX 4090.
- Each ships as its own isolated image (we build docling/MinerU/Chandra; olmOCR uses upstream); one pod per parser, batch-by-parser across the corpus. Conflicting torch/vLLM pins keep them apart.
- Local CPU is pymupdf4llm + GROBID for cheap lookups only, NOT in the comparison.
- Parse-once cache by SHA-256 of PDF bytes is mandatory. Never re-parse.

### Provenance — non-negotiable
- Every triple inserted into pyoxigraph carries (paper_hash, parser, page, bbox, run_id).
- If you cannot attach provenance, do not insert the triple.

### Schema — extensible by file, not by code
- New extraction domains (HER, CO2RR) ship as new SKILL.md folders.
- New slots: propose in `schema/exploratory.yaml`, never silently add to main schema.

### Anti-patterns — refuse on sight
- Adding a planner / critic / router agent.
- Adding LangGraph "because it makes the flow clearer."
- Exposing parsers as MCP servers.
- Vector search "for retrieval."
- Celery, Redis, Postgres.
- A web UI beyond the single-page provenance viewer.
- Running docling locally on M1.

### When to stop and ask
- The user mentions a feature not in the F1–F14 list. Confirm before building.
- A change would push total LOC above ~600. Confirm before continuing.
- A change would invalidate the prompt cache mid-session. Confirm.
- A dependency is not in pixi.toml. Confirm before adding.

These guidelines bias toward caution over speed. For trivial tasks, use judgment.
```

---

## Appendix B — Minimal directory layout

```
palimpsest/
├── CLAUDE.md
├── pixi.toml
├── README.md
├── pyproject.toml
├── src/palimpsest/
│   ├── __init__.py
│   ├── agent.py              # the loop (F2), ~80 LOC
│   ├── providers/
│   │   ├── anthropic.py      # Sonnet 4.5 + cache_control
│   │   ├── haiku.py
│   │   ├── deepseek.py
│   │   └── gemini.py
│   ├── tools/
│   │   ├── read_paper.py
│   │   ├── parse_pdf.py      # agent tool → parsers/runner.parse_with_cache
│   │   ├── extract.py        # LinkML + Sonnet + SHACL
│   │   ├── sparql.py         # query the pyoxigraph store
│   │   ├── open_notebook.py  # spawns marimo edit
│   │   └── read_skill.py
│   ├── parsers/
│   │   ├── gpu_provider.py   # RunPod context manager, one pod per parser (T14)
│   │   ├── runner.py         # parse_with_cache: batch-by-parser loop (T16, Appendix C)
│   │   └── commands.py       # parser registry: name → {template, run_cmd, output} (T16)
│   ├── cache.py              # SQLite parser cache (Appendix C)
│   ├── cost.py               # CostMeter, /budget live update
│   ├── store.py              # pyoxigraph wrapper
│   ├── versioning.py         # dulwich.porcelain wrappers
│   ├── tui/
│   │   ├── app.py            # Textual chat screen
│   │   └── slash.py          # /model /cost /budget ... (Appendix D)
│   └── viewer/
│       ├── app.py            # FastAPI
│       ├── templates/
│       └── static/pdfjs/     # vendored
├── schema/
│   ├── palimpsest.yaml       # LinkML, main
│   ├── exploratory.yaml      # agent-proposed slots
│   └── generated/            # pydantic, shacl, jsonld
├── skills/
│   └── oer-extraction/
│       └── SKILL.md
├── notebooks/                # marimo .py files, agent-generated
├── cache/                    # parser outputs by sha256
├── store/                    # pyoxigraph RocksDB
├── .git/                     # dulwich-managed for the graph
└── tests/
```

---

## Appendix C — Parser cache: SQL DDL + GPU lifecycle pseudocode

### C.1 SQLite DDL

```sql
CREATE TABLE papers (
  sha256      TEXT PRIMARY KEY,
  filename    TEXT NOT NULL,
  added_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  page_count  INTEGER,
  doi         TEXT
);

CREATE TABLE parser_runs (
  paper_sha256  TEXT NOT NULL REFERENCES papers(sha256),
  parser_name   TEXT NOT NULL CHECK (parser_name IN ('docling','mineru','olmocr','chandra')),
  parser_ver    TEXT NOT NULL,
  parsed_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  output_path   TEXT NOT NULL,            -- relative path under cache/
  gpu_seconds   REAL NOT NULL,
  gpu_cost_eur  REAL NOT NULL,
  run_id        TEXT NOT NULL,
  PRIMARY KEY (paper_sha256, parser_name, parser_ver)
);

CREATE TABLE cost_ledger (
  ts          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  kind        TEXT NOT NULL CHECK (kind IN ('llm','gpu')),
  provider    TEXT NOT NULL,
  amount_eur  REAL NOT NULL,
  detail      TEXT
);

CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
-- bootstrap:
INSERT INTO settings VALUES ('budget_eur', '50');
```

### C.2 `gpu_provider` lifecycle (pseudocode)

```python
# Parser registry (parsers/commands.py): one entry per isolated image. `run_cmd` builds
# the shell command for an (input, output) path pair; `template_id_env` names the env var
# holding that parser's RunPod template id. Commands are illustrative — the exact CLI is
# verified against each image in T16/T11-T13.
PARSERS = {
    "docling": {"template_id_env": "RUNPOD_TEMPLATE_DOCLING",
                "run_cmd": lambda i, o: f"docling {i} --to json --output {o}"},
    "mineru":  {"template_id_env": "RUNPOD_TEMPLATE_MINERU",
                "run_cmd": lambda i, o: f"mineru -b vlm -p {i} -o {o}"},
    "olmocr":  {"template_id_env": "RUNPOD_TEMPLATE_OLMOCR",
                "run_cmd": lambda i, o: f"python -m olmocr.pipeline {i} --output {o}"},
    "chandra": {"template_id_env": "RUNPOD_TEMPLATE_CHANDRA",
                "run_cmd": lambda i, o: f"chandra {i} --output {o}"},
}


class RunPodSession:
    """Generic pod lifecycle for ONE parser image. Parser-agnostic: the caller passes the
    template id (resolved from the registry); the session only does pod start/stop + ssh/scp
    (ssh / scp_up / scp_down per T14). Matches T14's constructor contract."""
    EUR_PER_USD = 0.92        # FX snapshot; update from a single FX endpoint

    def __init__(self, cost_meter, template_id, idle_soft=60, idle_hard=300):
        self.cost_meter = cost_meter
        self.template_id = template_id
        self.pod_id = None
        self.usd_per_hour = None    # read from the ACTUAL pod at __enter__ (varies by GPU/cloud)
        self.connect_ts = None
        self.last_activity = None
        self.idle_soft = idle_soft
        self.idle_hard = idle_hard

    def __enter__(self):
        pod = runpod_api.start_pod(template=self.template_id,
                                   gpu_type="RTX 4090", cloud="community")
        self.pod_id = pod["id"]
        # Bill at the pod's ACTUAL rate, not a hardcoded one — it varies by GPU type and
        # cloud (community / secure / spot). RunPod credits are USD-denominated (funded in
        # dollars at par), so costPerHr is USD/hr; adjustedCostPerHr reflects Savings Plans.
        self.usd_per_hour = pod.get("adjustedCostPerHr") or pod["costPerHr"]
        wait_for_ssh(self.pod_id, timeout=180)
        self.connect_ts = time.time()
        self.last_activity = self.connect_ts
        Thread(target=self._idle_watchdog, daemon=True).start()
        return self

    # ssh(cmd) / scp_up(local, remote) / scp_down(remote, local) per T14; each calls
    # self._touch() so the idle watchdog sees activity. Omitted here for brevity.

    def _idle_watchdog(self):
        while self.pod_id:
            idle = time.time() - self.last_activity
            if idle > self.idle_hard:
                self._teardown(reason="idle_hard_kill"); return
            if idle > self.idle_soft and not self._has_pending_work():
                self._teardown(reason="idle_soft_stop"); return
            time.sleep(5)

    def __exit__(self, *exc):
        if self.pod_id: self._teardown(reason="context_exit")

    def _teardown(self, reason: str):
        wall = time.time() - self.connect_ts
        runpod_api.stop_pod(self.pod_id)
        eur = wall / 3600 * self.usd_per_hour * self.EUR_PER_USD
        self.cost_meter.record_gpu(eur, detail=reason)
        self.pod_id = None


def parse_with_cache(pdf_paths, cost_meter, cache) -> dict[str, dict[str, Path]]:
    """Batch entrypoint: one pod PER PARSER, each running the whole corpus, then torn down.
    The returned mapping is COMPLETE (every sha × every parser) regardless of cache state —
    a cached output is filled from disk, an uncached one is parsed on the pod."""
    run_id = new_run_id()                            # one id for this batch invocation
    shas = {p: sha256_file(p) for p in pdf_paths}
    results: dict[str, dict[str, Path]] = {sha: {} for sha in shas.values()}

    for parser, spec in PARSERS.items():
        todo = []
        for p in pdf_paths:
            sha = shas[p]
            cached = cache.get_output(sha, parser)       # Path | None (T15 API)
            if cached is not None:                       # already cached for THIS parser
                results[sha][parser] = cached
            else:
                todo.append((p, sha))
        if not todo:                                     # parser fully cached → no pod
            continue
        template_id = os.environ[spec["template_id_env"]]
        with RunPodSession(cost_meter, template_id) as gpu:   # one pod, this parser's image
            for pdf_path, sha in todo:
                gpu.scp_up(pdf_path, f"/workspace/in/{pdf_path.name}")
                t0 = time.time()
                gpu.ssh(spec["run_cmd"](f"in/{pdf_path.name}", f"out/{sha}_{parser}.json"))
                secs = time.time() - t0
                out = cache.cache_dir / sha / f"{parser}.json"
                gpu.scp_down(f"/workspace/out/{sha}_{parser}.json", out)
                eur = secs / 3600 * gpu.usd_per_hour * RunPodSession.EUR_PER_USD
                # parser_ver: the parser's self-reported version string (T15). The whole
                # session's wall-clock is billed once to the CostMeter at _teardown; the
                # per-row eur here is an informational attribution in parser_runs only.
                cache.insert_parser_run(sha, parser, parser_ver, out, secs, eur, run_id)
                results[sha][parser] = out
    return results
```

**Batch flow rationale:** the four parsers can't share an image (their torch/vLLM pins conflict), so `parse_with_cache` loops **parser-first**: for each parser it spins one pod from that parser's image, runs the whole unseen corpus through it, then tears down before the next parser. That is 4 pod startups per batch instead of 1 — but each pod loads only its single model, and one startup is still amortized across all N papers (not the naïve "one pod per paper"). The 10–15 GB image pull dominates only the *first* cold start of each image; RunPod caches it host-side, so later pods start in ~90 s.

---

## Appendix D — Slash command table (with `/budget` live-update semantics)

| Command | Args | Effect |
|---|---|---|
| `/model` | `sonnet \| haiku \| deepseek \| gemini` | Switch active provider for next call. Invalidates prompt cache for this session. |
| `/cost` | — | Print today's spend, total spend, remaining headroom. Opens the cost dashboard screen. |
| `/budget` | `N` (EUR, integer) | **Live-update the hard cap to N. Persists to `settings.budget_eur` in SQLite. Prints new cap and `headroom = N − spent`. Effective immediately, no restart.** If `N < spent`, refuses with explanation. |
| `/parser` | `docling \| mineru \| olmocr \| chandra` | Pin a single parser for the next extraction call (default: agent picks based on skill recommendation). |
| `/skill` | `<name> \| list` | Load a skill by name into context, or list available skills. |
| `/compact` | — | Summarize conversation history into a single system note; reset messages; keeps cache prefix. |
| `/reset` | — | Drop conversation history entirely. Cache prefix preserved. |
| `/open-viewer` | — | Spawn FastAPI viewer (if not running) and print URL. |
| `/open-notebook` | `<name>` | Spawn `marimo edit notebooks/<name>.py`, print port. |
| `/quit` | — | Graceful shutdown: flush dulwich commit, tear down any GPU pod, close DB. |

**`/budget` implementation (concrete):**

```python
def slash_budget(arg: str) -> str:
    try:
        new_cap = int(arg)
    except ValueError:
        return f"usage: /budget N  (integer EUR)"
    spent = cost_meter.total_eur()
    if new_cap < spent:
        return (f"refused: spent €{spent:.2f} already exceeds requested cap €{new_cap}. "
                f"Use /budget {math.ceil(spent)+5} or higher.")
    with db.transaction():
        db.execute("UPDATE settings SET value=? WHERE key='budget_eur'", str(new_cap))
    cost_meter.cap = new_cap
    return (f"budget cap → €{new_cap}  "
            f"(spent €{spent:.2f}, headroom €{new_cap-spent:.2f})")
```

**CostMeter check (concrete):**

```python
class CostMeter:
    def __init__(self, db):
        self.db = db
        self.cap = float(db.fetch_one("SELECT value FROM settings WHERE key='budget_eur'"))
        self.soft = 0.8 * self.cap   # €40 at default

    def check_or_raise(self, projected_eur: float) -> None:
        spent = self.total_eur()
        if spent + projected_eur > self.cap:
            raise BudgetExceeded(spent=spent, cap=self.cap, projected=projected_eur)
        if spent + projected_eur > self.soft:
            ui.warn(f"approaching cap: €{spent+projected_eur:.2f}/€{self.cap}")
```

Every paid call site (`AnthropicProvider.complete`, `RunPodSession._teardown`) calls `check_or_raise` *before* incurring the spend, using a conservative projection (max output tokens × output rate).

---

## Appendix E — IRI annotation table for the OER schema slots

**Conventions:**
- **EMMO** = `https://w3id.org/emmo/domain/electrochemistry#electrochemistry_<hash>`
- **QUDT** = `http://qudt.org/vocab/unit/<symbol>`
- **PROV** = `http://www.w3.org/ns/prov#`
- **schema** = `http://schema.org/`
- **palimpsest** = `https://w3id.org/palimpsest/`

Where an EMMO term is not yet minted, palimpsest-local IRI is used with `skos:closeMatch` to the nearest EMMO concept, and a `TODO_EMMO_UPSTREAM:` comment in the schema YAML records what to request.

| LinkML slot | Range / unit (QUDT) | `slot_uri` | `close_mappings` / notes |
|---|---|---|---|
| `overpotential_at_10mAcm2` | float, mV (`qudt:MilliV`) | `palimpsest:overpotentialAt10mAcm2` | `skos:closeMatch emmo:electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6` (Overpotential). TODO_EMMO_UPSTREAM: request `OverpotentialAtBenchmarkCurrentDensity`. |
| `activation_overpotential` | float, mV | `emmo:electrochemistry_7fa406b0_512a_4d59_9e0c_5d8aba0103ae` | direct (ActivationOverpotential). |
| `anodic_overpotential` | float, mV | `emmo:electrochemistry_565c0b10_70fe_441a_b76a_b9a8e08ca7b7` | direct. |
| `tafel_slope` | float, mV/decade (`qudt:MilliV-PER-SEC` is wrong — use `palimpsest:mVPerDecade` with `qudt:hasQuantityKind` annotation; no QUDT term for "per decade") | `palimpsest:TafelSlope` | `skos:closeMatch emmo:electrochemistry_d48ea516_5cac_4f86_bc88_21b6276c0938` (ButlerVolmerEquation). TODO_EMMO_UPSTREAM: request `TafelSlope` and `TafelEquation` as siblings of `ButlerVolmerEquation` under `ElectrochemicalRelation`. |
| `exchange_current_density` | float, mA/cm² (`qudt:MilliA-PER-CentiM2`) | `emmo:ExchangeCurrentDensity` (class confirmed present in ECHO; resolve the hash at `electrochemistry.html#exchangecurrentdensity` at schema-generation time) | direct. |
| `charge_transfer_coefficient` | float, dimensionless | `emmo:electrochemistry_a4dfa5c1_55a9_4285_b71d_90cf6613ca31` | direct (Butler-Volmer α). |
| `ecsa` | float, m² or cm² (`qudt:M2` / `qudt:CentiM2`) | `emmo:ElectrochemicallyActiveSurfaceArea` (class confirmed present; resolve hash at `#electrochemicallyactivesurfacearea`) | direct. |
| `mass_activity` | float, A/g (`qudt:A-PER-GM`) | `palimpsest:massActivity` | TODO_EMMO_UPSTREAM. `skos:related emmo:electrochemistry_a3b53904_22b1_42a9_a515_c8a3aed7e841` (Electrocatalyst). |
| `turnover_frequency` | float, s⁻¹ (`qudt:PER-SEC`) | `palimpsest:turnoverFrequency` | TODO_EMMO_UPSTREAM. `skos:related` to Electrocatalyst. |
| `oer_reaction` | class | `palimpsest:OxygenEvolutionReaction` | **`skos:closeMatch emmo:electrochemistry_a0580fa9_5073_44af_b33e_7adbc83892d0` (AnodicReaction)**; `skos:broader emmo:electrochemistry_2e3e14f9_4cb8_45b2_908e_47eec893dec8` (ElectrodeReaction). TODO_EMMO_UPSTREAM: request `OxygenEvolutionReaction` as subclass of `AnodicReaction`. |
| `catalyst` | class | `emmo:electrochemistry_a3b53904_22b1_42a9_a515_c8a3aed7e841` | direct (Electrocatalyst). |
| `electrolyte_ph` | float, pH (`qudt:PH` — note QUDT's own caveat about pH dimensionality) | `palimpsest:electrolytePH` | `skos:related` to `emmo:AcidicElectrolyte` / `emmo:AlkalineElectrolyte` (both confirmed present in ECHO). |
| `electrode_potential_vs_rhe` | float, V (`qudt:V`) | `palimpsest:potentialVsRHE` | `skos:closeMatch emmo:ElectrodePotential`. TODO_EMMO_UPSTREAM: request reference-electrode-qualified subclasses (vs RHE, vs SHE, vs Ag/AgCl). |
| `scan_rate` | float, mV/s (`qudt:MilliV-PER-SEC`) | `palimpsest:scanRate` | `skos:related emmo:LinearPotentialRamp` (confirmed present). |
| `extracted_from` | URI (paper) | `prov:wasDerivedFrom` | PROV-O. |
| `extracted_by` | URI (parser run) | `prov:wasGeneratedBy` | PROV-O. |
| `parsed_by` | string (parser name+version) | `prov:wasAttributedTo` | PROV-O. |
| `bbox` | tuple[float,float,float,float] | `palimpsest:bbox` | local; page-relative coordinates `(x0,y0,x1,y1)`. |
| `page` | integer | `palimpsest:page` | local. |
| `doi` | string | `schema:identifier` | bibliographic. |
| `title` | string | `schema:name` | bibliographic. |
| `authors` | list[string] | `schema:author` | bibliographic. |

**The pattern:** prefer EMMO for concepts, QUDT for units, PROV for provenance, schema.org for bibliographic, palimpsest-local with explicit `skos:closeMatch` for everything EMMO has not yet minted — and write the TODO into the schema YAML so the gap is part of the thesis defence, not hidden.

### EMMO IRI lookup helper

```python
# src/palimpsest/ontology.py
from functools import cache
from rdflib import Graph, RDFS, OWL, URIRef
ECHO = "https://w3id.org/emmo/domain/electrochemistry"

@cache
def _echo() -> Graph:
    g = Graph()
    g.parse(ECHO, format="ttl")     # ~3 s, cached for session
    return g

@cache
def emmo_iri(class_label: str) -> str | None:
    """Resolve an EMMO ECHO class by its prefLabel. Returns full IRI or None."""
    g = _echo()
    for s, _, o in g.triples((None, RDFS.label, None)):
        if str(o) == class_label and (s, None, OWL.Class) in g:
            return str(s)
    return None

# usage at schema-gen time:
#   assert emmo_iri("Overpotential") == \
#     "https://w3id.org/emmo/domain/electrochemistry#electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6"
```

The schema generator runs this at build time to resolve the few IRI hashes that the subagent verification could not capture verbatim (`ExchangeCurrentDensity`, `ElectrochemicallyActiveSurfaceArea`, `OxygenElectrode`), and fails loudly if any of those classes have been renamed or removed in a future EMMO release.

---