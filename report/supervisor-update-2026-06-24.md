# palimpsest — benchmark results, cost, and next-phase request (2026-06-24)

*Follow-up to the 2026-06-19 meeting. This update reports the two benchmarks suggestion/decision; now executed on a 5-paper set; the spend to date; the knowledge-graph
and schema design; and two work-in-progress interfaces. Findings are stated as
**hypotheses** to be validated at larger scale, with a costed proposal and a funding
question at the end. Accuracy figures are scored against the gold **as it stood at run
time** — 41 tuples for the parser×model grid (§3), 40 for the multi-pass study (§4); the
current scorer holds 47 (see §2).*

---

## 1. Where it stands

The infrastructure is complete and the **two benchmarks suggestion/decision on 19 June are
executed** on a 5-paper reference set: 
1. the parser comparison (downstream extraction accuracy, parser held as the variable) 
2. the LLM-breadth study (frontier vs cheap
vs ensemble). 

Both share one deterministic scorer and one baseline design, so their
results are directly comparable. Alongside the benchmark, two interfaces reached
functional MVP — the **agent TUI** and the browser **verification viewer** — and the
run-time autonomy mechanisms raised on 19 June landed in code (a schema-reading tool, a
skill↔schema↔ontology consistency gate, run-time self-diagnosis of dropped extractions,
and a PEMWE-anode skill).

Honest split: **infrastructure and benchmark ≈ done on 5 papers; scale-up validation, testing and  writing remain.** Spend so far: **≈ \$35** (§5).

---

## 2. Benchmark methodology

### 2.1 Corpus and ground truth

Five Nature-family OER / PEM-electrolysis papers (Table 1). The reference was **not**
built by exhaustive manual labelling. For each paper we aggregated **multiple independent
reads** — the four parser text extractions plus a direct LLM read of the PDF (the
`*.pdfread.md` anchor) — **reconciled to consensus and spot-verified against the raw
parsed text**, with a human glance over samples. A value is admitted to the gold only if
it surfaces in at least one parser's text; values that exist only inside a figure are
recorded as a per-parser **coverage ceiling**, not as model failures.

Each gold entry is a **bare `(measurement-type, numeric-value)` tuple** — catalyst and
condition context are documented in the source tables but **stripped from the matching
logic** (a deliberate simplification with a known cost, §2.2). The set was curated
iteratively and the audit trail is kept visible:

- **41 → 40**: a gold audit (`experiments/results/gold_audit.md`, 2026-06-21) removed one
  mislabelled `Stability 2.5 h` — a measurement-window note, not an endurance benchmark.
- **40 → 47**: a later gold-thinness audit added **7 in-scope measurements** (six PEMWE
  full-cell voltages, one 400 h stability) that the original list under-scoped. Each
  candidate was gated by **≥3-model agreement first, then parser-text verification**
  ("agreement is a filter, not a verdict").

**Each published figure is scored against the gold as it stood when that run executed:**
the parser×model grid (§3, Table 2) on **41 tuples** (pre-audit), the multi-pass study
(§4) on **40** (post-audit, one mislabel removed). The current scorer holds the **47**-tuple
extension, on which the full grid has **not yet been re-scored** — that re-score is part of
the scaled run (§8). The runs differ by at most one tuple per paper and the rankings are
unaffected.

**Table 1 — the 5-paper reference set** (post-audit gold, 40 tuples).

| Paper | Journal (year) | System | Pages | Gold tuples |
|---|---|---|---|---|
| s41467-022-35426-8 | Nat. Commun. (2022) | Ir-Co₃O₄ single atoms | 12 | 19 |
| s41467-023-40912-8 | Nat. Commun. (2023) | IrO₂@TaB₂ | 12 | 7 |
| s41467-025-63541-9 | Nat. Commun. (2025) | Ir/TiOₓ@Ti | 14 | 4 |
| s41565-025-02030-y | Nat. Nanotechnol. (2025) | RuₓIrOₓ (figure-only Tafel) | 12 | 8 |
| s41929-024-01168-7 | Nat. Catal. (2024) | amorphous IrOₓ vs rutile | 13 | 2 |

*Total = 40 (post-audit). §3's grid was scored on the pre-audit 41-tuple gold (one extra
Stability tuple in row 5, later removed); the verified extension adds +3/+1/+3 to rows
2/3/4 → the current 47-tuple gold (19/10/5/11/2).*

**Baseline / floor.** A single design serves both studies: a floor configuration
(cheapest LLM + one reference parser + no domain skill — concretely `deepseek-v4-flash`
on MinerU, the locked runtime default) with each experiment varying **one axis** away
from it: the parser (→ parser study), the LLM (→ LLM study), or the skill.

### 2.2 Scoring — deterministic, meaning-blind

Matching is **deterministic Python, not an LLM and not regex** (`experiments/ab_extract.py`).
A prediction matches a gold tuple when (a) the measurement **type** is identical and (b)
the value is within the **looser of ±1 % relative or an absolute floor** (±0.5 for values
≥ 1, ±1×10⁻⁴ below 1). We report **precision = TP/(emitted)**, **recall = TP/(gold)**,
**F1**, and **\$ per correct extraction**. Before matching, values pass deterministic
normalisation: canonical-unit checking (tolerant of paper-faithful spellings, e.g. `s⁻¹`
≡ `1/s`), a generous per-slot magnitude ceiling that catches unconverted prefixes, and a
narrow milli-prefix unit re-derivation.

**What the scorer does and does not measure:** It measures *numeric* recall/precision on
type + value. It is **meaning-blind**: a value scores as correct even if it was extracted
for the wrong catalyst or condition, because the gold strips that context. **Semantic
correctness is not currently scored** — it is *enforced at graph-insert* (ontology typing + SHACL closed shapes + required provenance, §6), but condition-aware matching is a known
gap, not a feature. The LLM is used only for *extraction* (one call per page); scoring and
validation are entirely deterministic.

**On DeepEval (raised 19 June).** DeepEval's strength is LLM-as-judge scoring of *free
text*. Our task is *numeric* extraction, which a deterministic scorer answers without
added cost, run-to-run noise, or the circularity of grading LLMs with an LLM while
benchmarking LLMs. **Recommendation: deterministic scorer primary**, DeepEval noted and
available only as an optional fuzzy cross-check. *(Open — §10a.)*

**Parser count.** Four parsers enter the grid (docling, MinerU, dots.ocr, PaddleOCR).
**Chandra is excluded** — no bounding-box geometry, ~17 min/paper (\$0.105/paper) — and is
reported as "excluded: no geometry / timeout," never as IoU = 0.

---

## 3. Result A — parser-conditional accuracy (the thesis core)

**On the 5-paper set, the parser matters as much as the model.** Holding model and prompt
fixed, the *same* model's micro-recall swings 30+ points by parser alone, and switching
MinerU → docling raised raw micro-recall for **8 of 9 models**. docling emits roughly an
order of magnitude more, finer-grained text spans than MinerU's coarse blocks, so figure-
and table-derived values become citable: the figure-only Tafel slopes in the RuₓIrOₓ paper
move from a **4/8 ceiling on text-only parsers to 8/8 on docling**. This is the thesis's
headline claim, demonstrated at small scale.

**Table 2 — best model per parser** (raw, micro-recall, full-5-paper models only;
41-tuple pre-audit gold). The partial sonnet-paddle row is excluded as not comparable.

| Parser | Best model | Recall | Cheap alternative |
|---|---|---|---|
| MinerU | deepseek-v4-pro | 88 % | gemini-flash-lite 83 % |
| docling | sonnet-4.6 | 95 % | gemini-flash-lite 93 % (~12× cheaper) |
| dots.ocr | gemini-3.5-flash (free) | 88 % | — (\$0) |
| PaddleOCR | deepseek-v4-pro | 93 % | gemini-3.5-flash 92 % (\$0) |

Parser ranking for ceilings: **docling ≳ dots ≈ paddle > MinerU**. Once off MinerU, the
best model is parser-robust enough that the *model* choice moves accuracy more.

---

## 4. Result B — frontier single-shot vs cheap + ensemble

**Best overall model: `gemini-3.1-flash-lite`** — 0.80 average µF1, 81–93 % recall on
*every* parser, at **\$0.0011 / correct**. Robustness across parsers is the deciding
property for an agent that may run any parser.

**The "cheap + loop VS frontier-single-shot" question — supported, conditionally**
(recall on the 40-tuple gold; the multi-pass arms ran on docling + paddle):

| Combination | Recall | vs frontier |
|---|---|---|
| **model-union** (deepseek-flash ∪ gemini-lite, 1 shot each), docling | **100 %** (40/40) | ≥ best clean single-shot (sonnet 95 %), **\$0 marginal** |
| model-union, paddle | **95 %** (38/40) | ≥ best clean single-shot (deepseek-pro 93 %) |
| gemini-lite + requery, docling | **98 %** (39/40) | = sonnet single-shot, ~12× cheaper |
| gemini-lite raw, docling | 92 % | already > GPT-5.4 single-shot (88 %) |

The winning move is **model-union of two *cheap* models** — they miss *different* values
(decorrelated errors), so unioning their single-shot outputs reaches frontier recall at
essentially zero marginal cost (the cells were already paid for). *(Frontier yardsticks:
sonnet-4.6 is a clean 5/5 row on docling; on paddle it ran only 2/5 papers, so the paddle
comparison uses the clean deepseek-pro/gemini rows instead.)*

**But multi-pass is not a free lunch**, and the nuance is the point:
- **reason-first** (CRANE-style reason-then-format) is **catastrophic** on the weakest
  cheap model — deepseek-flash ~94 % → 40 % at an 8k output cap (the reasoning field eats
  the token budget and truncates items), recovering only to 75 % at 16k, still below plain
  raw. It does **not** transfer to a token-budget-limited extraction model.
- **requery** helps the *strong* cheap model (gemini-lite 92→98) but **hurts** the weak
  one (deepseek-flash). The loop must be matched to the model.
- The locked default **`deepseek-v4-flash` is the worst model overall** (0.47 avg µF1,
  too parser-fragile) — cheap only until you price its misses. **It should be replaced**
  (→ `deepseek-v4-pro`, steady ~88 % everywhere, or → gemini-flash-lite). *(Open — §10c.)*
- The expensive ceiling bought little: **opus-4.8** cost \$0.0338/correct (~30× the cheapest
  viable models) yet scored *below* deepseek-pro and sonnet, and was pruned after Stage 1.

**Recommended production combo: docling + `gemini-3.1-flash-lite`** (0.86 F1, 93 %
recall, \$0.0011/correct); or docling/paddle + free `gemini-3.5-flash` (88–92 %, \$0) when
\$0 outweighs the F1 gap.

---

## 5. Cost to date

**Table 3 — spend (cost ledger `palimpsest.db` + actual RunPod, 2026-06-24).**

| Category | \$ | Notes |
|---|---|---|
| **LLM total** | **25.98** | 901 metered calls across the model×parser×multipass grid |
| — OpenAI (GPT-5.4 / -mini) | 11.69 | the dearest tier, mid-pack accuracy |
| — Anthropic (sonnet / haiku / opus) | 8.41 | includes the pruned opus-4.8 (\$1.73) |
| — Google (gemini-lite / -flash) | 3.32 | best value, used most (210 + 49 calls) |
| — DeepSeek (pro / flash) | 2.09 | flash heavily tested (276 calls), flagged for retirement |
| — other (qwen, minimax) | 0.47 | dropped models, retained data |
| **GPU / RunPod (actual)** | **≈ 9.40** | 5-parser cloud verification (see note) |
| **Total** | **≈ 35.4** | remaining headroom ≈ \$14.6 |

**GPU note.** The in-process cost meter books only the GPU spend it drives directly
(**\$1.80**, 12 sessions in the ledger); real RunPod spend is **≈ \$9.40** — the difference
is un-metered pod wall-time (previous runs, image pull, idle, setup), which by design is outside the
in-process meter (implemented later) and is the operator's responsibility. The honest total is **≈ \$35.4**.

The entire 4-parser × ~9-model grid plus the multipass arms cost ≈ \$26 of LLM; the **cheap
models dominate the accuracy-per-dollar frontier** (≈30× cost spread, opus vs gemini-lite,
per correct extraction). The expensive models bought little accuracy.

---

## 6. Knowledge graph, schema, and ontology

**What becomes a triple:** Each extracted measurement is one RDF node, **typed by its
ontology class**, carrying `value` (xsd:float) + `unitLabel` (string) + optional
`confidence`, and linked to two nodes: a **Condition** (current density, electrode
potential vs RHE, temperature, scan rate, electrolyte family + pH, cell type, iR
correction, …) and an **Evidence** node typed `prov:Entity` carrying the
**provenance treated as non-negotiable** — paper SHA-256, page, four bbox floats,
parser name, and source text. Run metadata (run_id, parser run, **extraction-model tag**)
is written to a **per-run named graph**, keeping the data graph SHACL-closed. A
measurement lacking complete provenance is **refused, not inserted**. (One Overpotential
emits ~22 quads: measurement 5, evidence 9, paper 4, condition 3, run-graph 1.)

**What is in the schema, and why:** A single **LinkML** file (`schema/palimpsest.yaml`)
is the source of truth; it generates **Pydantic + JSON-Schema + JSON-LD + SHACL** so one
contract simultaneously validates extraction, shapes the LLM's tool signature, and
enforces RDF conformance. It defines a **measurement hierarchy of 11 types** (Overpotential,
TafelSlope, ExchangeCurrentDensity, ChargeTransferCoefficient, MassActivity,
TurnoverFrequency, ECSA, SpecificActivity, Stability, PEMWECellVoltage, DegradationRate)
plus the structural classes Paper, Condition, Electrolyte, and Evidence. New slots are proposed in
`schema/exploratory.yaml` and reviewed before entering the closed main schema — never
silently added.

**How the ontology models the values:** Alignment is at two levels. **In the triples**:
each measurement node is typed by an **EMMO ECHO** electrochemistry class IRI where one
exists (e.g. Overpotential, ExchangeCurrentDensity, ECSA), or by a palimpsest-local IRI
where EMMO has no term (TafelSlope, MassActivity, the PEMWE metrics, OER); provenance uses
**PROV-O**; bibliography uses **schema.org**. **At the schema level** (mappings/annotations,
not emitted as triples): **QUDT** units and **H2KG v1.0.0** equivalences are attached via
`skos:closeMatch` — H2KG already defines 3 of our 4 hand-rolled metrics, so aligning to it
also aligns us to an official DECODE/Helmholtz standard. The value is stored today as a
flat `float` + unit string rather than H2KG's relational `Measurement → hasProperty →
QuantityValue` node; bridging to that shape is future work.

**Current store.** The working RDF store holds **14,637 quads across 60 extraction-run
named graphs** — this reflects every model×parser combination inserted during
benchmarking, not five papers' worth of unique measurements. A new **append-only
corrections** path lets a human *or* the agent supersede a value with an immutable audit
chain (a sanctioned second graph-write path that doubles as extractor feedback).

---

## 7. These are hypotheses, not claims

Everything above holds on **5 papers / 40 gold tuples**. Stated as hypotheses to test at
scale:

- **H1** — a parser-robust cheap model (gemini-flash-lite) matches frontier single-shot
  accuracy at ~10× lower cost.
- **H2** — model-union of two decorrelated cheap models closes the gap to frontier at ≈\$0
  marginal cost.
- **H3** — docling is the best general-purpose parser for downstream extraction;
  parser-union is the reliable closer for figure-only values.

**Generalization risk we are watching honestly:** the extraction guards (magnitude
ceilings; milli-prefix unit re-derivation) were tuned against *these 5 papers* and took
three review rounds to stop corrupting their own test spans — an overfitting signal. We
will treat the 20–25-paper run as the generalization test and **relax rather than patch**
if a guard misfires. **Precision caveats both ways:** a gold-thinness audit of 105 apparent
false-positive groups found **~32 (≈30 %) are real values the gold omitted** (precision is
understated) but also **~52 (≈50 %) are likely hallucinations** (the genuine precision
loss) — so precision is neither as good nor as bad as a raw count suggests, and is the axis
that most needs the larger corpus.

---

## 8. Next phase — cost projection and funding request

Two distinct activities, two very different costs:

**(a) Application / demo run (the 19-June use case).** 20–25 hydrogen papers through the
chosen pipeline (docling + gemini-flash-lite), driven by the agent end-to-end. Parsing is
docling-only here, so GPU is small and extraction ≈ \$0.15; **total ≈ \$1–2** plus margin if any crashes occur and **agent api cost ≈ \$1–2**.

**(b) Full re-benchmark at 20–25-paper scale (validating H1–H3, and re-scoring on the
47-tuple gold).** Re-running the parser × model × multipass grid at 5× the corpus:

| Item | Estimate |
|---|---|
| Parse 20–25 papers × 4–5 parsers (GPU, actual rates) | **≈ \$30-40** |
| LLM grid (4 parsers × ~8 models × multipass), ~5× the 5-paper spend | **≈ \$120–150** |
| Ground-truth construction (multi-read + verification, human spot-check) | principal *effort* cost |
| **Total compute** | **≈ \$150–190** |

*(The \$30 parse line uses real RunPod rates, ~5× the in-process meter — see §5; the earlier
naive estimate of \$6 undercounted pod overhead.)*

**Funding question.** The validation run is what turns the hypotheses into thesis claims,
and it is the part that breaks the \$50 self-imposed budget (current spend ≈ \$35; ≈ \$14.6
left vs ≈ \$150–180 needed). **Is Jülich able to support the scaled validation** — as
API/GPU credits or a raised budget on the order of **\$150–200** to cover compute plus a
margin? The projection is transparent so the figure is defensible; the demo run (a)
proceeds regardless within the current cap.

---

## 9. Agent TUI and verification viewer (work in progress)

Both are functional MVPs; figures attached (TUI still + GIF, viewer stills + GIF).

**Agent TUI ("Scriptorium").** A chat-first terminal interface to the constrained-autonomy
agent: natural-language requests drive the tool-using loop, with **live tool traces**
(supervision-relevant tools shown in full), streaming replies, a **cost-meter footer**
(spend / cap, model roster), and cost-free slash commands — `/cost`, `/budget N`,
`/model`, `/use <role> <provider>`, `/resume`. *(Figure: `tui-demo.gif`.)*

**Verification viewer (browser).** A two-pane FastAPI + PDF.js page: the source PDF on the
left, extracted measurement cards on the right. A **parser × model matrix** filters the
view; **clicking a card highlights the exact source bounding box** over the PDF (provenance
you can see); confidence badges, an **edit/correction form** (correct, flag, or comment —
appended as a superseding correction), and CSV export. Docling bboxes are paragraph-level
today; pixel-parser bbox scaling is the active WIP. *(Figures: `current-viewer.png`,
`paddle-bbox.png`, `phase-d-edit.png`; `viewer-demo.gif`.)*

These directly serve the **Accessible** FAIR dimension: a reviewer verifies a value against
its page region before relying on it.

---

## 10. Questions for the supervisor

a. **Scorer.** Agree to the deterministic scorer as primary, DeepEval as an optional
   secondary cross-check?
b. **Parser count.** Report four parsers in the grid, Chandra documented as excluded (no
   geometry / timeout) — confirm?
c. **Default model.** Approve replacing the locked `deepseek-v4-flash` default with
   `deepseek-v4-pro` (safe drop-in) or `gemini-3.1-flash-lite` (best overall)?
d. **Funding.** Is Jülich support available for the scaled validation run (§8b, ≈ \$150–200)?
e. **Ground truth at scale.** What reference protocol for the 20–25 papers — multi-read +
   verification as here, how many papers get a human-checked reference, and is meaning-aware
   (condition-context) scoring worth adding, given it is not scored today (§2.2)?
f. **Open invitation.** Any other thoughts on the approach taken — the benchmark design,
   the cheap-model/ensemble direction, the constrained-autonomy framing, or the H2KG
   alignment?

---

*Figures trace to: `experiments/results/FINDINGS.md`, the `*.meta.json` snapshots,
`experiments/corpus_manifest.csv`, `experiments/results/gold_audit.md`, the `palimpsest.db`
cost ledger (+ actual RunPod), the live `store/`, and `schema/palimpsest.yaml` /
`src/palimpsest/store.py`. Reproducible reports: `reports/t72_report.html`,
`reports/t74_report.html`.*
