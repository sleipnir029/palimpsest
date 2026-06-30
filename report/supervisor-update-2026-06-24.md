This report summarises the current status of palimpsest and the results of an initial
benchmarking study, following the meeting of 19 June 2026. It covers the two benchmarks
agreed at that meeting, now executed on a five-paper reference set; the expenditure to
date; the design of the knowledge graph and schema; and two interface components under
active development. The findings are presented as hypotheses to be validated at larger
scale, together with a costed proposal for that validation. Unless noted otherwise,
accuracy figures are computed against the reference set as it stood when each run was
executed: 41 measurements for the parser-by-model grid (Section 3) and 47, the current
reference set, for the multi-pass study (Section 4); see Section 2.

## Status

The extraction and benchmarking infrastructure is complete, and the two benchmarks
proposed on 19 June have been executed on a five-paper reference set: (i) a comparison of
PDF parsers measured by downstream extraction accuracy, with the parser as the independent
variable, and (ii) a study of language-model breadth spanning frontier, inexpensive, and
ensemble configurations. Both use a single deterministic scoring rule and a common
baseline design, so the two are directly comparable. Two interface components have reached
a minimum viable state: the agent terminal interface and a browser-based verification
viewer. The run-time autonomy mechanisms discussed on 19 June have been implemented,
namely a schema-reading tool, a consistency gate linking skill, schema, and ontology,
run-time self-diagnosis of dropped extractions, and a domain skill for the PEM
water-electrolysis anode. The agent's bash escape hatch is now confined to the workspace
by an operating-system sandbox (macOS Seatbelt or Linux bwrap), which strengthens the
constrained-autonomy property that forms the core of the thesis.

In summary, the infrastructure and the benchmark are complete on five papers; scale-up
validation, further testing, and writing remain. Expenditure to date is approximately
\$35 (Section 5).

## Benchmark methodology

### Corpus and ground truth

The corpus comprises five papers on the oxygen-evolution reaction and PEM water
electrolysis, drawn from the Nature family of journals (Table 1). The reference set was
not produced by exhaustive manual labelling. For each paper, several independent readings
were aggregated, namely the text extracted by the four parsers together with a direct
language-model reading of the PDF (the `*.pdfread.md` anchor), and these were reconciled
to a consensus and spot-checked against the raw parsed text, with a human review of a
sample. A value is admitted to the reference set only if it appears in at least one
parser's text; values that occur only within a figure are recorded as a per-parser
coverage ceiling rather than as model failures.

Each reference entry is a bare `(measurement-type, numeric-value)` pair. The catalyst and
the experimental conditions are recorded in the source tables but are not used by the
matching procedure, a deliberate simplification whose cost is discussed in Section 2.2.
The reference set was curated iteratively, and the audit trail is retained:

- From 41 to 40: a review (`experiments/results/gold_audit.md`, 21 June 2026) removed one
  mislabelled entry, `Stability 2.5 h`, which denotes a measurement window rather than an
  endurance result.
- From 40 to 47: a later completeness review added seven in-scope measurements (six
  PEM full-cell voltages and one 400 h stability value) that the original list had
  omitted. Each candidate was admitted only after agreement among at least three models
  and subsequent verification against the parsed text; agreement served as a filter, not
  as a verdict.

Each published figure is therefore scored against the reference set as it stood when that
run was executed: the parser-by-model grid (Section 3, Table 2) against the pre-audit
41-measurement set, and the multi-pass and ensemble study (Section 4) against the current
47-measurement set. The two differ by the seven measurements added in the completeness
review. The frontier models in the grid have not yet been re-scored on the 47-measurement
set, so Section 4 compares the inexpensive ensemble against the grid's frontier figure only
approximately; that re-score forms part of the scaled run (Section 8).

**Table 1.** The five-paper reference set (post-audit reference, 40 measurements).

| Paper | Journal (year) | System | Pages | Reference measurements |
|---|---|---|---|---|
| s41467-022-35426-8 | Nat. Commun. (2022) | Ir-Co₃O₄ single atoms | 12 | 19 |
| s41467-023-40912-8 | Nat. Commun. (2023) | IrO₂@TaB₂ | 12 | 7 |
| s41467-025-63541-9 | Nat. Commun. (2025) | Ir/TiOₓ@Ti | 14 | 4 |
| s41565-025-02030-y | Nat. Nanotechnol. (2025) | RuₓIrOₓ (figure-only Tafel) | 12 | 8 |
| s41929-024-01168-7 | Nat. Catal. (2024) | amorphous IrOₓ vs rutile | 13 | 2 |

The total is 40 after the audit. The grid in Section 3 was scored on the pre-audit
41-measurement set (one additional stability value in the last row, later removed); the
verified extension adds three, one, and three measurements to rows 2, 3, and 4
respectively, giving the current 47-measurement set (19, 10, 5, 11, 2).

The baseline design is shared by both studies. A floor configuration is defined as the
least-expensive model with a single reference parser and no domain skill, concretely
deepseek-v4-flash on MinerU, the locked runtime default. Each study then varies one
factor away from this floor: the parser (the parser study), the language model (the model
study), or the skill.

### Scoring

Matching is performed by deterministic code, not by a language model and not by regular
expressions (`experiments/ab_extract.py`). A prediction matches a reference value when
the measurement type is identical and the value lies within the looser of a 1 % relative
tolerance or an absolute floor (±0.5 for values of magnitude at least one, ±1×10⁻⁴ below
one). The reported metrics are precision (true positives over emitted values), recall
(true positives over reference values), the F1 score, and the cost per correct
extraction. Before matching, values are normalised deterministically: canonical units are
checked (tolerating paper-faithful spellings, for example s⁻¹ and 1/s), a generous
per-slot magnitude ceiling catches unconverted prefixes, and a narrow milli-prefix unit
re-derivation is applied.

It is important to state what the scorer does and does not measure. It measures numeric
recall and precision on type and value only. It is deliberately context-blind: a value is
counted as correct even if it was extracted for the wrong catalyst or condition, because
the reference set omits that context. Semantic correctness is therefore not scored at
present. It is, however, enforced when a value is written to the graph, through ontology
typing, closed-shape SHACL validation, and mandatory provenance (Section 6).
Condition-aware matching remains a known gap rather than a feature. The language model is
used only for extraction (one call per page); scoring and validation are entirely
deterministic.

On the question of DeepEval, raised on 19 June: DeepEval is designed for
language-model-as-judge scoring of free text, whereas the present task is numeric
extraction, which a deterministic scorer answers without additional cost, without
run-to-run variance, and without the circularity of using a language model to grade
language models during a model benchmark. A deterministic scorer is therefore proposed as
the primary metric, with DeepEval reserved, if used at all, for an optional fuzzy
cross-check.

Four parsers enter the grid: docling, MinerU, dots.ocr, and PaddleOCR. Chandra is
excluded because it emits no bounding-box geometry and requires about 17 minutes per paper
(\$0.105 per paper); it is reported as excluded on these grounds rather than as a zero
intersection-over-union score.

## Parser-conditional extraction accuracy

Across the five-paper set, the choice of parser affects accuracy as strongly as the choice
of model. With the model and prompt held fixed, a single model's micro-averaged recall
varies by more than 30 percentage points across parsers, and replacing MinerU with docling
raised raw micro-recall for eight of the nine models tested. docling produces roughly an
order of magnitude more, and finer-grained, text spans than MinerU's coarse blocks, so
values reported in figures and tables become citable; the figure-only Tafel slopes in the
RuₓIrOₓ paper rise from a ceiling of four of eight on the text-only parsers to eight of
eight on docling. This is the central empirical claim of the thesis, demonstrated here at
small scale.

**Table 2.** Best model per parser (raw extraction, micro-recall, models with complete
five-paper coverage; 41-measurement pre-audit reference). The partial sonnet-on-PaddleOCR
row is excluded as not comparable.

| Parser | Best model | Recall | Inexpensive alternative |
|---|---|---|---|
| MinerU | deepseek-v4-pro | 88 % | gemini-flash-lite 83 % |
| docling | sonnet-4.6 | 95 % | gemini-flash-lite 93 % (about 12× cheaper) |
| dots.ocr | gemini-3.5-flash (free) | 88 % | (none; \$0) |
| PaddleOCR | deepseek-v4-pro | 93 % | gemini-3.5-flash 92 % (\$0) |

For recovery ceilings the parsers rank docling ≳ dots.ocr ≈ PaddleOCR > MinerU. Once
MinerU is set aside, the better models are sufficiently robust across parsers that the
choice of model has the larger effect on accuracy.

## Frontier, inexpensive, and ensemble configurations

The most accurate single model across the full parser grid is gemini-3.1-flash-lite, with
a mean µ-F1 of 0.80, recall of 81 to 93 % depending on the parser, and a cost of \$0.0011
per correct extraction (the grid of Section 3, scored on the 41-measurement reference).
Robustness across parsers is the decisive property for an agent that may invoke any parser.

The multi-pass and ensemble study was run on docling and PaddleOCR and is scored on the
current 47-measurement reference, so its figures are reproducible directly from the stamped
results table (`experiments/results/llm_matrix_t74_2026-06-21.csv`). The single-run recall
of an inexpensive model is consequently lower here than the corresponding entry in Table 2:
gemini-lite recovers the same 38 values in both cases, which is 93 % of the pre-audit
41-measurement set but 81 % of the extended 47, the difference being the seven added PEM and
stability measurements that a single inexpensive run misses.

| Configuration | Recall (47-measurement) | Effect |
|---|---|---|
| gemini-lite, single run, docling | 81 % (38/47) | baseline for the strategies below |
| gemini-lite with re-query, docling | 87 % (41/47) | a within-model second pass recovers three further values |
| Union of deepseek-flash and gemini-lite (one run each), docling | 100 % (47/47) | the two models' errors are decorrelated; the union is complete |
| The same union, PaddleOCR | 91 % (43/47) | near-complete; the residual is not all recoverable from PaddleOCR's text |

The most effective configuration is the union of two inexpensive models, each run once.
Because the two models omit different values, that is, their errors are decorrelated, the
union recovers all 47 reference measurements on docling at negligible marginal cost, the
individual runs having already been performed; the seven PEM and stability measurements
that defeat a single inexpensive run are exactly those the union recovers. A within-model
re-query is more limited: it raises gemini-lite from 81 to 87 % on docling but does not
reach completeness. The best frontier single run on the earlier 41-measurement grid
(sonnet-4.6 on docling, 95 %, Table 2) is of the same order as the union; a like-for-like
re-score of the frontier models on the 47-measurement reference has not yet been performed
and forms part of the scaled run (Section 8). The proposition that an ensemble of
inexpensive models reaches frontier-level recall at a fraction of the cost is therefore
supported on docling, and is stated as hypothesis H2 for validation at larger scale.

Multi-pass strategies are not uniformly beneficial.

- A reason-then-format strategy, in the manner of CRANE, fails on the weakest inexpensive
  model: deepseek-flash falls from 94 % (its plain single-run recall) to 40 % at an 8k
  output limit, because the reasoning field exhausts the token budget and truncates the
  items, and recovers only to 66 % at a 16k limit, still below plain extraction. It does
  not transfer to an extraction model constrained by output length.
- A targeted re-query is two-edged: it raises the stronger inexpensive model (gemini-lite,
  81 to 87 % on docling) but lowers the weaker one (deepseek-flash, 94 to 89 %); the
  strategy must be matched to the model.
- The locked default, deepseek-v4-flash, is the weakest model overall on the grid (mean
  µ-F1 0.47) and too sensitive to the parser to serve as a default; its low nominal cost is
  offset by its misses. We propose replacing it with deepseek-v4-pro (a steady 88 % or so
  on every parser) or with gemini-flash-lite.
- The most expensive model returned little: opus-4.8 cost \$0.0338 per correct extraction,
  about 30 times the least-expensive viable models, yet scored below deepseek-pro and
  sonnet on the grid, and was removed after the first stage.

The recommended production configuration is docling with gemini-3.1-flash-lite, the best
single parser-and-model pairing on the grid (Section 3), supplemented where completeness
matters by a second inexpensive model whose output is unioned with the first; where a zero
marginal cost is decisive, the free gemini-3.5-flash is a strong baseline on docling and
PaddleOCR.

## Cost to date

**Table 3.** Expenditure (cost ledger `palimpsest.db` and actual RunPod usage, as of
24 June 2026).

| Category | \$ | Notes |
|---|---|---|
| LLM total | 25.98 | 901 metered calls across the model, parser, and multi-pass grid |
| of which OpenAI (GPT-5.4, -mini) | 11.69 | the most expensive tier, mid-ranked accuracy |
| of which Anthropic (sonnet, haiku, opus) | 8.41 | includes the pruned opus-4.8 (\$1.73) |
| of which Google (gemini-lite, -flash) | 3.32 | best value, used most (210 and 49 calls) |
| of which DeepSeek (pro, flash) | 2.09 | flash heavily tested (276 calls), proposed for retirement |
| of which other (qwen, minimax) | 0.47 | dropped models, data retained |
| GPU / RunPod (actual) | about 9.40 | five-parser cloud verification (see note) |
| Total | about 35.4 | remaining headroom about \$14.6 |

The in-process cost meter records only the GPU expenditure it drives directly (\$1.80
across 12 sessions). Actual RunPod expenditure is approximately \$9.40; the difference is
un-metered pod wall-time (earlier runs, image download, idle, and setup), which by design
lies outside the in-process meter and is the operator's responsibility. The honest total
is therefore approximately \$35.4.

The full grid of four parsers and roughly nine models, together with the multi-pass arms,
cost approximately \$26 in language-model calls. The inexpensive models dominate the
accuracy-per-dollar frontier, with a spread of about 30 times between opus and gemini-lite
per correct extraction; the most expensive models contributed little additional accuracy.

## Knowledge graph, schema, and ontology

Each extracted measurement becomes a single RDF node, typed by its ontology class and
carrying a value (`xsd:float`), a unit label (string), and an optional confidence. It is
linked to two further nodes: a condition node (current density, electrode potential versus
the reversible hydrogen electrode, temperature, scan rate, electrolyte family and pH, cell
type, iR correction, and so on) and an evidence node typed `prov:Entity` that carries the
provenance treated as non-negotiable, namely the paper SHA-256, the page, four
bounding-box coordinates, the parser name, and the source text. Run metadata (run
identifier, parse run, and the extraction-model tag) is written to a per-run named graph,
which keeps the data graph closed under SHACL. A measurement that lacks complete provenance
is refused rather than inserted. A single overpotential measurement emits about 22 quads
(five for the measurement, nine for the evidence, four for the paper, three for the
condition, and one in the run graph).

The schema is defined once, in a single LinkML file (`schema/palimpsest.yaml`), which is
the source of truth. From it are generated the Pydantic models, the JSON schema, the
JSON-LD context, and the SHACL shapes, so that one contract simultaneously validates
extraction, shapes the language model's tool signature, and enforces conformance of the
RDF. The schema defines a measurement hierarchy of eleven types (overpotential, Tafel
slope, exchange current density, charge-transfer coefficient, mass activity, turnover
frequency, ECSA, specific activity, stability, PEM cell voltage, and degradation rate),
together with the structural classes Paper, Condition, Electrolyte, and Evidence. New
slots are proposed in `schema/exploratory.yaml` and reviewed before they enter the closed
main schema; they are never added silently.

Ontology alignment operates at two levels. In the triples themselves, each measurement
node is typed by an EMMO ECHO electrochemistry class IRI where one exists (for example,
overpotential, exchange current density, and ECSA), or by a palimpsest-local IRI where
EMMO provides no term (Tafel slope, mass activity, the PEM metrics, and the
oxygen-evolution reaction). Provenance uses PROV-O, and bibliographic metadata uses
schema.org. At the schema level, as annotations rather than emitted triples, QUDT units
and H2KG (version 1.0.0) equivalences are attached through `skos:closeMatch`. H2KG already
defines three of the four metrics that were originally local, so aligning to it also
aligns the work to a recognised DECODE and Helmholtz standard. Values are at present stored
as a flat number with a unit string, rather than in the relational form that H2KG uses
(measurement, hasProperty, quantity value); bridging to that form is future work.

The working RDF store currently holds 14,637 quads across 60 extraction-run named graphs.
This reflects every model-and-parser combination inserted during benchmarking, rather than
the unique measurements of five papers. A recently added, append-only corrections path
allows a human or the agent to supersede a value with an immutable audit chain; this is a
sanctioned second write path to the graph that also serves as feedback to the extractor.

## Status of the findings

All results above rest on five papers and 40 reference measurements, and are stated as
hypotheses for validation at larger scale:

- H1: a parser-robust inexpensive model (gemini-flash-lite) matches frontier single-run
  accuracy at roughly one tenth of the cost.
- H2: the union of two inexpensive models with decorrelated errors closes the gap to
  frontier accuracy at negligible marginal cost.
- H3: docling is the best general-purpose parser for downstream extraction, and the union
  of parsers is the reliable means of recovering figure-only values.

A risk to generalisation should be stated plainly. The extraction guards (the magnitude
ceilings and the milli-prefix unit re-derivation) were tuned against these five papers and
required three rounds of review before they stopped corrupting their own test spans, which
is a sign of over-fitting. The 20-to-25-paper run will be treated as the test of
generalisation, and a guard that misfires will be relaxed rather than further patched.
Precision carries a caveat in both directions: a completeness review of 105 apparent
false-positive groups found that about 32 (roughly 30 %) are real values that the
reference set omits, so precision is understated, while about 52 (roughly 50 %) are likely
hallucinations and represent the genuine loss. Precision is thus neither as high nor as low
as a raw count would imply, and it is the axis that most needs the larger corpus.

## Proposed next phase and cost projection

The next phase comprises two activities of very different cost.

The first is an application, or demonstration, run, corresponding to the use case
discussed on 19 June: 20 to 25 papers on hydrogen technology passed through the chosen
pipeline (docling with gemini-flash-lite), driven end-to-end by the agent. Parsing here
uses docling only, so GPU cost is small and extraction costs about \$0.15; the total is
approximately \$1 to \$2, with a small margin for any failures. This run fits within the
current budget.

The second is a full re-benchmark at the scale of 20 to 25 papers, which would validate
hypotheses H1 to H3 and re-score on the 47-measurement reference. It re-runs the grid of
parsers, models, and multi-pass arms at five times the present corpus size:

| Item | Estimate |
|---|---|
| Parse 20 to 25 papers across four or five parsers (GPU, actual rates) | about \$30 to \$40 |
| Model grid (four parsers, about eight models, multi-pass), about 5× the five-paper spend | about \$120 to \$150 |
| Ground-truth construction (multi-reading, verification, human spot-check) | principally an effort cost |
| Total compute | about \$150 to \$200 |

The parse estimate uses actual RunPod rates, about five times the in-process meter
(Section 5); an earlier estimate of \$6 had under-counted pod overhead.

The full re-benchmark is what would convert the present hypotheses into defensible thesis
claims, and it requires roughly \$150 to \$200, which exceeds the budget available to the
project. We would therefore be grateful to know whether Forschungszentrum Jülich is able
to support the scaled validation, whether as API or GPU credits or as an increased budget
of the order of \$150 to \$200. The estimate is itemised above so that the figure can be
assessed independently, and the demonstration run can proceed within the current budget in
any case.

## Agent interface and verification viewer

Both components are functional and at a minimum viable state. Figures are attached: a still
of the terminal interface, and stills of the viewer. A screencast of the agent terminal
interface in use is available at https://youtu.be/bWA27LkR4hQ.

The agent terminal interface (theme "Scriptorium") is a conversational front end to the
constrained-autonomy agent. Replies stream as they are produced; each tool invocation
appears as a collapsible trace with its elapsed time, with the supervision-relevant tools
(`bash` and `extract_paper`) shown in full and the others summarised. A footer shows a
budget gauge (a live expenditure bar that moves from sepia through amber to red across
graduated warning thresholds), an issue badge, and the true context size, alongside
clickable links and a copy-reply action. Fifteen cost-free slash commands are available,
covering expenditure (`/cost`, `/budget`), model routing (`/use <role> <provider>`), the
session (`/resume`, `/clear`, `/export`, `/undo`), and provenance and audit (`/view` for
the viewer, `/git` for the workspace checkpoints, `/issues`, and `/review` for an agent
summary of the session), together with switchable themes (`/theme`).

The verification viewer is a two-pane page (FastAPI with PDF.js): the source PDF on the
left, and on the right a parser-by-model matrix selector together with three tabs that
follow the extraction pipeline. The first tab, Parser, shows the raw text spans the parser
recovered; the second, Schema, shows the typed measurement cards derived from them (slot,
value, unit, confidence badge, page, source text, and an edit action); the third, Gold,
shows that cell scored against the reference set (true positives over total, recall,
precision, and the matched or missed status of each reference value). The Gold tab reuses
the benchmark's own matching procedure, so the numbers a reviewer sees are identical to the
benchmark's. Selecting any card or span highlights its source region on the PDF; that
region is now narrowed to the exact value text by means of the PDF text layer, giving a
precise highlight rather than a whole paragraph. Parsers that report pixel coordinates are
scaled to the page, and parsers without geometry decline to draw a box rather than draw a
wrong one. The viewer also supports append-only corrections (by a human or the agent), CSV
export, and graceful degradation. The tabbed viewer is complete; narrowing the stored
geometry across all parsers is in progress.

Together these components serve the Accessible dimension of the FAIR principles, and the
tabbed viewer mirrors the thesis itself: it follows the same parser-to-schema-to-reference
path that the benchmark measures, with every value traceable, by a single click, to the
region of the page from which it was read.

## Open questions

The following points would benefit from the supervisor's guidance.

- Scoring metric. We propose a deterministic scorer as the primary metric and suggest that
  DeepEval, if used at all, serve only as a secondary fuzzy cross-check. Would this be
  acceptable?
- Parser count. We propose reporting four parsers in the grid and documenting Chandra
  separately as excluded (no bounding-box geometry; prohibitive run time). Is this
  appropriate?
- Default model. We would like to replace the locked deepseek-v4-flash default with either
  deepseek-v4-pro or gemini-3.1-flash-lite, and would welcome your view.
- Funding. Would Forschungszentrum Jülich be able to support the scaled validation run
  (Section 8, second item; approximately \$150 to \$200)?
- Ground truth at scale. What reference protocol would you recommend for the 20 to 25
  papers: the multi-reading-and-verification approach used here; how many papers should
  receive a human-checked reference; and would meaning-aware (condition-context) scoring be
  worth adding, given that it is not scored at present (Section 2.2)?
- Any further comments. We would be glad of any further thoughts on the approach, whether
  on the benchmark design, the inexpensive-model and ensemble direction, the
  constrained-autonomy framing, or the H2KG alignment.

The figures and numbers in this report trace to `experiments/results/FINDINGS.md`, the
`*.meta.json` snapshots, `experiments/corpus_manifest.csv`,
`experiments/results/gold_audit.md`, the `palimpsest.db` cost ledger together with actual
RunPod usage, the live `store/`, and `schema/palimpsest.yaml` with
`src/palimpsest/store.py`. The reproducible benchmark reports are
`reports/t72_report.html` and `reports/t74_report.html`.
