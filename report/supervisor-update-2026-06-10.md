# palimpsest — status & H2KG integration findings (2026-06-10)

## Where it stands

The full extraction **infrastructure** is built and unit-tested:

- agent loop, cost meter (€50 hard cap), direct Anthropic SDK with prompt caching;
- 5-parser orchestration on RunPod (docling, MinerU, Chandra, dots.ocr, PaddleOCR) with a
  parse-once cache keyed by SHA-256;
- a LinkML schema with EMMO ECHO + QUDT mappings, generating Pydantic + SHACL + JSON-LD;
- schema-guided LLM extraction, SHACL validation, and a pyoxigraph RDF store with PROV-O
  provenance.

What remains is the **scientific core**: the pipeline has **not yet run end-to-end on real GPU
hardware**, and there is **no corpus run, no parser-comparison metrics, and no thesis chapters**
yet. Honest split: **infrastructure ≈ 85%, scientific results ≈ 0%.** The five demonstrator PDFs
are in `papers/` (`s41565-025-02030-y`, `s41467-023-40912-8`, `s41929-024-01168-7`,
`s41467-025-63541-9`, `s41467-022-35426-8`).

## H2KG integration — verified against the live v1.0.0 ontology

**Strongly positive and worth doing.** I inspected the published H2KG ontology directly (the
resolvable Turtle at `https://w3id.org/h2kg/hydrogen-ontology` plus the PEMWE-profile alignment
files), not just the release page.

- H2KG **reuses the same EMMO ECHO module** palimpsest already binds to
  (`emmo/domain/electrochemistry`) and ships **PEMWE (PEM water electrolysis) and PEMFC**
  profiles that exactly cover our domain.
- **H2KG already defines 3 of the 4 metrics we had hand-rolled as local classes** —
  `h2kg:TafelSlope`, `h2kg:MassActivity`, `h2kg:TurnoverFrequency` — plus the ECHO-bound ones we
  already use (Overpotential, ECSA, ExchangeCurrentDensity, ChargeTransferCoefficient). Aligning
  lets us drop local vocabulary and point at an official DECODE/Helmholtz standard.

Two honest caveats:

1. **Structural model differs.** H2KG models a measurement relationally
   (`Measurement → hasParameter / hasProperty → Property`, with a `QuantityValue` node for
   magnitude+unit), whereas our store currently writes a flat `value + unit string`.
2. **Each side holds half the metric alignment.** H2KG's metrics are local `h2kg:Property` terms
   **not** anchored to ECHO class IRIs; ours **are** ECHO-typed and carry explicit QUDT units. So
   a `skos` cross-link completes the alignment, and we can contribute the ECHO/QUDT anchoring
   (and an OER→`AnodicReaction` bridge that neither side has natively) back upstream.

**Verdict:** H2KG is a **combined / layered** alignment — domain naming authority on top of our
EMMO/QUDT/PROV backbone — **not** a single-source replacement, and not "seamless" until one
correctness gap is fixed first.

## The gap that gates everything (priority)

Our RDF graph currently **drops experimental conditions** (current density, electrolyte, pH,
temperature, reference electrode) at insert time. A metric stored without its conditions — e.g. an
overpotential without "at *X* mA/cm² in *Y* electrolyte vs RHE" *(illustrative; exact figures per
paper)* — is **not a comparable datum**. These conditions are exactly the `Parameter` content
H2KG's relational model expects, so fixing this is **both** the top scientific-validity fix **and**
the prerequisite for any H2KG export. Two further provenance-integrity items follow: bounding
boxes are presently LLM-transcribed rather than read from parser geometry (and Chandra emits no
geometry at all), and extracted units are not validated against the schema's canonical units.

## Plan

1. **Fix the graph** to store conditions and match the schema (correctness + H2KG prerequisite).
2. **Align the schema to H2KG** (the concrete "we integrated H2KG" deliverable; schema-only).
3. **Verify the 5 parsers on a real GPU** (the one thing mocks cannot cover).
4. **Fix bbox/unit provenance** so the parser-comparison metrics measure parsers, not the LLM.
5. **Run the corpus** and write the parser-comparison + ontology-gap chapters.

Budget remains comfortably within the €50 cap. Detailed task cards: `tasks/T46`–`T49`, with
`T25` and `T43` amended. Full technical assessment available on request.
