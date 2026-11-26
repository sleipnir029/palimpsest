# Working in palimpsest as a coding agent

This file is for coding agents (Claude Code, Codex, OpenCode, Cursor, Gemini CLI and
similar) opened in this repository. palimpsest turns research PDFs into an
ontology-aligned RDF knowledge graph. Every value is checked in code and carries its
provenance (paper hash, parser, page, bounding box, run).

You can be the extraction model yourself, so the user needs **no API key**. The checks
stay in code: you propose measurements, and palimpsest accepts or rejects them.

## Setup

Run every command from the repository root.

```bash
pixi install                # Python 3.11 env (macOS arm64 or linux-64)
pixi run test               # optional: the offline test suite
```

## Extract measurements from a paper (no API key)

The example papers in `papers/` ship with their parser outputs in `cache/`.

1. Write the prompt:
   ```bash
   pixi run python -m palimpsest prompt papers/s41467-022-35426-8.pdf --out workspace/prompt.md
   ```
   Options: `--parser docling|mineru|dots|paddle` (default `docling`) and
   `--skill oer-extraction|pemwe-anode` (default `oer-extraction`).
2. Read `workspace/prompt.md` to the end (it is 100–150 KB, so read it in chunks) and
   follow its SYSTEM section. The USER section lists the whole paper as numbered text
   spans `[id] (pN) text`. If one paragraph appears in spans on two pages, cite the span
   on the page where the number is printed.
3. Write ONLY the JSON answer it asks for to `workspace/answer.json`. Cite span ids for
   every value. Never invent a value or a span id.
4. Ingest it with the exact command printed at the top of the prompt. Span ids belong
   to one parser, so `--parser` and `--skill` must match step 1:
   ```bash
   pixi run python -m palimpsest ingest papers/s41467-022-35426-8.pdf --parser docling --skill oer-extraction --response workspace/answer.json
   ```
   It prints `n_extracted / n_validated / n_inserted`, then the reason for every dropped
   item (a cited span that doesn't contain the value's digits, a unit that doesn't fit
   the quantity, a record outside the schema). Report those to the user; don't work
   around them. Each `ingest` adds a new run, so ingesting the same answer twice
   duplicates values: to fix drops, ingest only the corrected items.

The schema has no catalyst field: the catalyst a value belongs to is in its stored
source text (`palim:sourceText` on the evidence). Read it from there when the user asks
"which catalyst".

## Query the graph

```bash
pixi run python -c "from palimpsest.tools.graph_summary import graph_summary; print(graph_summary())"
pixi run python -c "from palimpsest.tools.sparql_query import sparql_query; print(sparql_query('''
PREFIX emmo: <https://w3id.org/emmo/domain/electrochemistry#>
SELECT * WHERE { ?s ?p ?o } LIMIT 20'''))"
pixi run viewer             # http://localhost:8765, click a value to see it on the PDF page
```

`pixi run python -c "from palimpsest.tools.graph_summary import describe_schema; print(describe_schema())"`
lists the measurement classes and predicates to use in SPARQL. The viewer holds the
graph store's lock while it runs, so stop it before `ingest` or the query one-liners.

## Rules

- Write only inside `workspace/` (notebooks, notes, answers).
- Don't edit `src/`, `schema/`, `store/` or `cache/` to make a value pass. Checks fail
  for a reason.
- Insert into the graph only through `ingest` (or the app's own extraction), never by
  writing RDF directly. That is how provenance stays attached.
- Domain knowledge lives in `skills/<group>/<name>/SKILL.md`. Read the relevant skill
  before extracting or analysing.
- New schema slots are proposals: add them to `schema/exploratory.yaml`, never to
  `schema/palimpsest.yaml`.

## With an API key instead

`pixi run tui` starts palimpsest's own agent (terminal UI), and
`pixi run python -m palimpsest "<request>"` runs one turn. Both need an LLM key in `.env`;
see `.env.example` and the README.
