# Working in palimpsest as a coding agent

This file is for coding agents (Claude Code, Codex, OpenCode, Cursor, Gemini CLI and
similar) opened in this repository. palimpsest turns research PDFs into an
ontology-aligned RDF knowledge graph. Every value is checked in code and carries its
provenance (paper hash, parser, page, bounding box, run).

You can be the extraction model yourself, so the user needs **no API key**. The checks
stay in code: you propose measurements, and palimpsest accepts or rejects them.

## Setup

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
2. Read `workspace/prompt.md` completely and follow its System section. The User section
   lists the paper as numbered text spans `[id] (pN) text`.
3. Write ONLY the JSON answer it asks for to `workspace/answer.json`. Cite span ids for
   every value. Never invent a value or a span id.
4. Ingest it:
   ```bash
   pixi run python -m palimpsest ingest papers/s41467-022-35426-8.pdf --response workspace/answer.json
   ```
   The command prints `n_extracted / n_validated / n_inserted`. Items fail when a cited
   span doesn't contain the value's digits, when units don't reduce correctly, or when
   the record doesn't fit the schema. Report those failures to the user; don't work
   around them.

## Query the graph

```bash
pixi run python -c "from palimpsest.tools.graph_summary import graph_summary; print(graph_summary())"
pixi run python -c "from palimpsest.tools.sparql_query import sparql_query; print(sparql_query('''
PREFIX emmo: <https://w3id.org/emmo/domain/electrochemistry#>
SELECT * WHERE { ?s ?p ?o } LIMIT 20'''))"
pixi run viewer             # http://localhost:8765, click a value to see it on the PDF page
```

`pixi run python -c "from palimpsest.tools.graph_summary import describe_schema; print(describe_schema())"`
lists the measurement classes and predicates to use in SPARQL. RocksDB allows one writer
at a time, so stop the viewer before you run `ingest`.

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
