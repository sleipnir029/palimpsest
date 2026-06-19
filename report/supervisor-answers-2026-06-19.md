# Answers to the 19-06-2026 supervisor questions

This document responds point-by-point to the concerns raised in the 2026-06-19
meeting (`meetings/19-06-2026.md`). It states, for each concern, what already
exists in the system (verified against the code and `PROGRESS.md`), what is
genuinely missing, and the proposed plan. Status claims here are grounded in the
codebase as of 2026-06-19, not aspirations.

---

## 0. Framing: FAIR, the gap, and how palimpsest mitigates it

The opening of the thesis should be the FAIR argument, which the report already
states (`report/palimpsest-report.md` §1.1):

> "Measured against this standard, the quantitative content of the primary
> literature is largely non-compliant: the measurements are findable as PDFs but
> not as data, are not interoperable because they lack a shared vocabulary, and
> are not reusable without human intervention for each value."

Palimpsest mitigates each FAIR dimension by construction:

| FAIR dimension | Current non-compliance | Palimpsest mechanism | Status |
|---|---|---|---|
| **Findable** | values locked in PDF prose/tables | each measurement is a node in a SPARQL-queryable RDF graph, keyed by paper SHA-256 | working |
| **Accessible** | re-reading each PDF by hand | provenance viewer: click a value → see the source page region (bbox) it came from | spec'd / partial |
| **Interoperable** | no shared vocabulary | EMMO ECHO + QUDT + PROV-O + H2KG alignment via a single LinkML schema | working for OER |
| **Reusable** | units/conditions implicit, no provenance | every triple carries value + unit + experimental conditions + full provenance (paper, parser, page, bbox, run_id) | working |

**Honest scope note.** The report at one point calls the agent "domain-agnostic"
(§1.2). We should retire that phrasing. The defensible claim — which the report's
own conclusion already makes (§7) — is: *"we demonstrate how a domain is added,
with electrocatalysis as the worked instance, and claim nothing about fields not
yet attempted."* The contribution is a **constrained-autonomy agent that runs
robustly within a domain for which a skill + ontology alignment has been
authored**, plus a documented, reproducible method for authoring that skill. Not
push-button domain generality.

---

## 1. Benchmarking: two studies, one shared design

Both studies share a single scoring rule and a single baseline design, so the
results are directly comparable.

**Scoring rule (the metric).** A predicted measurement counts as correct when it
matches a ground-truth label on: (a) the right slot (e.g. overpotential vs Tafel
slope), (b) value within tolerance (10 % relative, or ±0.5 for small integers),
and (c) the right unit. From correct/incorrect/missing counts we report
**precision, recall, and F1** per condition. This is deterministic and already
implemented in prototype form in `experiments/ab_extract.py`.

**Baseline design (answering "what is the baseline and how do we decide it").**
The supervisor asked this for *both* parsers and LLMs. One scheme covers both:

- **Ceiling = an aggregated reference (silver standard).** Hand-labelling the full
  corpus isn't feasible, so the reference is built by reading each PDF with several
  strong models and aggregating to consensus (the T35 pattern: multiple drafters +
  independent adversarial reviewers; a human glances over a sample). Scored as the
  reference everything else is compared against. **Caveat:** for the LLM study,
  reference built by LLMs that are also under test is circular — mitigate by including
  a panel model *not* in the test matrix, scoring only high-consensus items, and
  human spot-checks. The parser study is unaffected (LLM fixed, parser varied).
- **Floor = a defined baseline configuration**, namely
  `cheapest-LLM + one reference parser + no domain skill`.
- **Each experiment varies one axis** away from the floor (an ablation):
  - vary the **parser** (fixing LLM + skill) → the parser study;
  - vary the **LLM** (fixing parser + skill) → the LLM study;
  - add the **skill** (fixing parser + LLM) → shows the skill's contribution.

This makes "the baseline" concrete and identical across both studies, and lets us
attribute each accuracy gain to a specific cause.

### 1a. Parser benchmark (tasks T36–T39)

Four metrics, against the aggregated reference (silver standard, see §1 baseline):

| Task | Metric | What it measures |
|---|---|---|
| T36 | text accuracy (normalised Levenshtein, `rapidfuzz`) | transcription fidelity |
| T37 | table-cell F1 | table-structure recovery |
| T38 | bbox IoU (% with IoU > 0.5) | localisation accuracy |
| T39 | **downstream extraction accuracy by parser** | **the headline metric** |

T39 is the thesis's principal claim: hold the LLM fixed, vary the parser, measure
how accurately the fixed model recovers the intended measurements from each
parser's output. This is *downstream* accuracy, distinct from transcription
fidelity — a parser can transcribe perfectly yet lay text out in a way that
defeats extraction, or vice versa.

### 1b. LLM benchmark (the breadth-matrix study)

Rather than only comparing frontier models, the LLM study asks a sharper,
FAIR-relevant question: **does structured scientific extraction actually require a
large model, or can a small / local model recover the same numbers cheaply?** We
compare across tiers, all scored by the same deterministic rule:

- **Frontier cloud:** Claude, GPT;
- **Cheap cloud:** DeepSeek, Gemini-flash;
- **Small open:** Qwen (e.g. 7B / 32B);
- **Local:** a model run on local hardware (Ollama / vLLM / llama.cpp).

We report precision/recall/F1 **and cost per paper and latency**, so the result is
an accuracy-vs-cost frontier, not just a ranking. A finding that a cheap or local
model matches a frontier model on numeric extraction directly supports the FAIR /
reproducibility / budget argument: cheaper extraction means more science can be
made reusable.

### 1c. On DeepEval

The meeting noted DeepEval. DeepEval is an LLM-evaluation framework whose strength
is judging *free-text* answers (an LLM-as-judge scores another LLM's prose against
criteria; plus RAG-style metrics). Our task is **numeric extraction**, where the
question is "did it recover 236 mV at 10 mA/cm² within tolerance" — a deterministic
recall/precision/F1, which `ab_extract.py` already computes. An LLM-judge here adds
cost, run-to-run nondeterminism, and a mild circularity (using an LLM to grade LLMs
while we are benchmarking LLMs). **Recommendation: use a deterministic scorer as
the primary metric.** DeepEval can be mentioned as the recognised framework and, if
desired, used only for a secondary fuzzy-match cross-check. *(Open for discussion —
see §4.)*

### 1d. A correction: five parsers, not four

The meeting notes say "4 parsers." The system implements **five** (docling, MinerU,
Chandra, dots.ocr, PaddleOCR). In practice the comparison currently uses **four**,
because **Chandra produces no bounding-box geometry** (so it cannot enter the bbox
metric T38) and reproducibly times out (>40 min/paper) on figure-dense Nature
papers, so it was dropped from the parsed corpus (`PROGRESS.md` T34). We should
decide explicitly and state it in the thesis: report four parsers across all
metrics, and report Chandra separately as "excluded — no geometry / timeout," never
as IoU = 0.

---

## 2. Ontology, skills, and the agent: the real autonomy question

The supervisor's gap questions — *how does the agent know the ontology? how are
skills created for a new domain? how does it use the ontology to build the graph,
and is it actually using it?* — are the heart of the thesis. The honest answer
requires distinguishing two things that are currently conflated.

**Build-time vs run-time intelligence.** Today, several correctness problems were
fixed not by the agent but by a human plus reviewer subagents *while building the
system*, and then locked with regression tests. Documented examples:

- an enum advertised to the model but not modelled in the schema produced zero
  valid extractions, fixed in T50;
- those same enum slots were then silently dropped at graph-insert time — caught by
  an **independent reviewer subagent**, fixed, and pinned with a correlated SPARQL
  test (T50 / T25);
- a skill's hand-typed table once pointed at deleted schema slots (F2).

In every case the **agent did not detect the problem itself** — a human or a
build-time review did. That is the true gap. It does not mean the data is being
dropped now (those specific bugs are fixed and tested); it means the safety net is
*build-time review*, which will not be present when the agent is run on a new
domain on its own.

**The fix: move that competence into the agent, as five code-enforced mechanisms.**
This is "constrained autonomy enforced in code," and it is the thesis contribution:

1. **The skill declares its ontology alignment** — names the target (H2KG PEMWE
   profile) and maps each domain concept → schema class → IRI. *(Today this is
   prose in `SKILL.md` and drifts; example F2.)*
2. **The schema is a readable contract** — a `read_schema` tool lets the agent read
   classes, slots, units, and IRIs at run time. *(Today the schema is embedded as a
   JSON blob in the extraction prompt; the agent loop never sees it.)*
3. **A consistency gate runs at skill-load** — automatically verifies that every
   class/slot the skill names exists in the schema and that its IRI resolves in
   H2KG/EMMO; refuses or warns otherwise. *(Today: nothing — drift is human-caught.)*
4. **Run-time error surfacing** — the agent sees "N items routed to errors / enum X
   not in schema" and can react, instead of relying on a human reading the logs.
5. **Provenance records the ontology + version per triple** — so "is it actually
   using the ontology?" becomes a SPARQL query, not a matter of trust.

Mechanism #3 is the direct answer to "how are skills created for a new domain and
how do we know they're correct": the gate makes a malformed skill fail loudly at
load, so authoring a new skill is checkable rather than hopeful.

**Which ontology, and how it's created.** Per the supervisor's instruction we align
to **H2KG** (the hydrogen-technology ontology, PEMWE profile). H2KG reuses the same
EMMO ECHO electrochemistry module the schema already binds, and already defines
three of our four hand-rolled metrics (`TafelSlope`, `MassActivity`,
`TurnoverFrequency`) — these alignments are **already in the schema** (T47,
verified). So aligning to H2KG also aligns us to EMMO, and the genuine remaining
gap — neither H2KG nor EMMO defines OER as a native reaction class — becomes a
small, real upstream contribution. Skill + alignment *authoring* is a
human-supervised, LLM-assisted process (Claude or ChatGPT are both fine — it is a
build-time method, documented as contribution #4), not an autonomous capability.
The autonomy is in *running* the skill, not authoring it.

---

## 3. What is done vs missing (verified 2026-06-19)

| Area | Status | Evidence |
|---|---|---|
| Agent loop, 5 parsers on RunPod, parse-once SHA-256 cache, cost meter | **done** | `PROGRESS.md` T08/T16/T50; `cache.py`, `cost.py` |
| End-to-end pipeline PDF → graph | **done** | `pipeline.py`; `demo` CLI; T25 |
| Conditions stored on each measurement | **done** (commit `eea87d2`) | `store.py:187–193` + correlated SPARQL test in `test_pipeline.py` |
| Parser-native bbox (LLM no longer transcribes) | **done** | T49 → T51 span-projection |
| H2KG alignment for OER metrics | **done** | T47, 7 metrics `skos:closeMatch`, live fragment tests |
| LLM extraction (Anthropic-wire: DeepSeek default + Claude) | **done** | `providers/`; €0.0041–0.0084/paper |
| Ground truth | **partial** | 5 papers × 4 parsers, grounded; chandra dropped (T34/T35) |
| `read_schema` tool, skill↔schema consistency gate, run-time error surfacing | **missing** | grep-confirmed: no such tool, no gate in `skills.py` |
| New hydrogen skill beyond OER | **missing** | only `skills/oer-extraction/` |
| Parser metric scorers T36–T39 | **missing** | only `ab_extract.py`, `parse_corpus.py` |
| LLM breadth-matrix benchmark (Gemini/Qwen/local adapters) | **missing** | only Anthropic-wire providers |
| 20–25 paper hydrogen demo run | **deferred** | T34 deferred until parser comparison picks parsers |
| Thesis chapters T42–T44, demo T45 | **missing** | — |

Summary: the **infrastructure is largely complete and the headline data-validity
problems (conditions, bbox, H2KG-OER) are already solved**; the remaining work is
(a) the run-time autonomy mechanisms, (b) one new hydrogen skill, (c) the benchmark
scorers + LLM matrix, (d) the demo run, and (e) the writing.

---

## 4. Open decisions to confirm with the supervisor

1. **DeepEval**: agree to a deterministic scorer as the primary metric, with
   DeepEval mentioned and optionally used only for a secondary cross-check?
2. **Parser count in the thesis**: report four parsers, Chandra documented as
   excluded (no geometry / timeout) — confirm.
3. **LLM matrix breadth**: confirm the tiers (frontier / cheap / small-open /
   local). Adding OpenAI/Qwen/local needs no new SDK (HTTP via `httpx`, an
   experiment-only path), so it does not disturb the locked runtime stack.
4. **Domain scope**: the actual corpus (`papers/paper list/`) is overwhelmingly
   IrO₂/TiO₂ OER anodes for PEM water electrolysis — so the "new skill" is a PEMWE-anode
   extension of the existing OER skill, not a separate HER domain (confirm). Ground truth
   is built by multi-LLM PDF-read + aggregation (no hand-labelling) — agree the panel
   composition and how many papers get a reference.
