---
name: ontology-extension
description: Propose extensions (new classes, mappings, slot/unit anchors) to EMMO ECHO and H2KG, grounded in evidence already in the graph. Covers what an ontology is and is not, the ECHO and H2KG term shapes, and the SKOS/SSSOM mapping rules a proposal must satisfy. Use when the researcher asks to extend, align, or contribute back to the upstream ontologies.
when_to_use: user asks to extend an ontology, propose a new class or mapping, close an alignment gap, or contribute a term upstream
version: 1.0.0
kind: task
reads:
  - Measurement
  - TafelSlope
  - MassActivity
  - TurnoverFrequency
  - SpecificActivity
  - Stability
  - PEMWECellVoltage
  - DegradationRate
  - Electrolyte
  - OxygenEvolutionReaction
  - Evidence
  - Paper
uses:
  - read_file
  - search
  - sparql_query
  - check_skill
---

# Ontology extension playbook

You are proposing terms for ontologies other people maintain. Every rule below was
**measured** from the pinned artefacts by `experiments/ontology_conventions.py`, not
copied from documentation — where the docs and the data disagreed, the data won.

## 1. What an ontology is not

This is where proposals fail. An ontology is a **TBox**: the kinds of things that can
exist and how they relate. It is not a database schema, not a taxonomy of your data,
and not a place to record measurements.

Never propose a class for:

- **An instance or a measured value.** `IrO2Overpotential10mAcm2` is not a class. It is
  a measurement of an instance under a condition — that belongs in the graph (ABox),
  which palimpsest already populates.
- **A value bundled with its condition.** `TafelSlopeInAcid` conflates a quantity with
  a parameter. Model the quantity once; the condition is a separate assertion.
- **A convenience grouping for your application.** "Metrics we extract" is a view, not
  a kind of thing.
- **A term that already exists.** Check first, always. See §5.

If you cannot say what would make something an *instance* of the proposed class, it is
probably not a class.

## 2. The two upstreams are structurally different — this is not cosmetic

One gap renders **twice**, and the two renderings are not stylistic variants:

| | EMMO ECHO | H2KG |
|---|---|---|
| A metric is a | `owl:Class` | `owl:NamedIndividual` typed to an upper class |
| Scale | 927 ECHO-local classes (230 restrictions on them; 2,894 across the merged closure) | 19 classes, **2,176** terms, **0 restrictions** |
| Identifier | opaque UUID hash IRI | readable fragment |
| Axioms | real DL ontology | effectively a SKOS vocabulary in OWL clothing |

So `TafelSlope` is a **class** in an ECHO rendering and an **individual**
(`a h2kg:Property`) in an H2KG rendering. Emitting one in the other's shape is a
hard error, not a style issue.

Consequence you must respect: **H2KG has no restrictions and 7 `subClassOf` triples in
total.** Do not propose axioms, restrictions, or hierarchy for H2KG. There is nothing
there to attach them to.

## 3. ECHO term shape

Required on every proposed ECHO class. Presence rates over the 927 ECHO-local classes:

- `skos:prefLabel`, **exactly one**, CamelCase — present on 100%
- `rdfs:label`, exactly one — present on 100%
- an **`elucidation`** (or `definition`, or `conceptualisation` — any one suffices;
  `emmocheck.test_description` accepts any of the three) — 100% have at least one
- at least one `rdfs:subClassOf` — 100%
- IRI of the form `electrochemistry_<uuid4 with underscores>` in ECHO's namespace —
  99.5% conformant

**Language tags are a separate, weaker convention — do not confuse them with presence.**
Every ECHO-local class has a `prefLabel`, but only **90.5%** have one that is `@en`-tagged
throughout (88 carry a plain literal). `elucidation` is tagged 99.8% of the time. Tag
yours `@en`; just do not assume upstream always did.

**Write an elucidation, not a definition.** They are different things. A *definition*
claims necessary and sufficient conditions; an *elucidation* is deliberately weaker — a
bridge to reality for a concept that cannot be formally defined without circularity.
EMMO's top-level terms are primitives, so elucidation is the norm. Only write a
`definition` if you are also proposing an `owl:equivalentClass` axiom.

**Quantities take two parents**, not one: a dimensional parent that fixes the unit, and
a domain parent that places it in electrochemistry. `echo:Overpotential` is `subClassOf
ElectricPotential` **and** `subClassOf ElectrochemicalQuantity`;
`echo:ExchangeCurrentDensity` is `subClassOf ElectricCurrentDensity` **and**
`ElectrochemicalKineticQuantity`. A quantity with only a domain parent will be
challenged — `emmocheck`'s `test_quantity_dimension` exists to enforce the other half.

**What ECHO does NOT require, despite its own documentation saying otherwise:** an
external definition source. Only 26.8% of ECHO-local classes cite one, and
`hasIUPACName` / `ISO80000Reference` / `qudtReference` are at **0%** — those live in
the EMMO core layer. Cite IUPAC when you have it; do not treat it as mandatory, and do
not invent a citation to satisfy a rule that does not exist.

## 4. H2KG term shape

Required on every proposed H2KG term (measured per type — the requirements genuinely
differ by type):

- `skos:prefLabel` `@en` — required for every type
- `dcterms:description` `@en` — required for every type (100% across the board)
- `h2kg:hasQuantityValue` — required for **`Parameter` and `Property` only** (~97%);
  absent by design on `Matter`, `Instrument`, `Manufacturing`, `Data`
- `skos:altLabel` — advisory; 67–88% depending on type

`h2kg:appliesToProfile` and `rdfs:isDefinedBy` are **not** conventions: 0% across every
type in the released base artefact. Do not emit them.

`Parameter` vs `Property` is the type decision that matters: **`Property` = a measured
output, `Parameter` = a simulation or experimental input.** An overpotential you
measured is a `Property`; an exchange current density you fed to a model is a
`Parameter`.

## 5. Mappings

Check for an existing term **before** proposing a new one. Two failure modes:

- **The term already exists**, sometimes under a label you did not search for. Proposing
  it again is a duplicate; propose a **mapping** instead. Search `skos:altLabel` as well
  as `prefLabel` — ECHO records abbreviations there, so a term you know by its acronym
  may be filed under its spelled-out name.
- **The false friend.** A label match is **not** a meaning match. ECHO contains 16
  classes whose labels are duplicated across namespaces (this is why
  `ontology.emmo_iri()` raises on an ambiguous label instead of guessing), and EMMO core
  carries general-physics quantities whose names collide with electrochemical ones.
  **Always read the candidate's `elucidation` and its parents before mapping to it.** A
  term sitting under an unrelated branch is a different concept wearing the same word,
  and mapping to it is worse than proposing nothing.

Predicate choice, per SSSOM:

- `skos:exactMatch` — the same concept. Transitive: if someone else asserts B ≡ C, you
  have implicitly asserted A ≡ C. Use sparingly.
- `skos:closeMatch` — rough equivalence, deliberately non-transitive. SSSOM warns it is
  ambiguous, but it is the honest predicate for a palimpsest `owl:Class` ↔ an H2KG
  **individual**, because `exactMatch` there would assert class/individual
  interchangeability. That is why the existing 9 H2KG alignments use it.
- `skos:broadMatch` / `narrowMatch` — one is more general. Never assert alongside
  `exactMatch` on the same pair.
- **Never** use `owl:equivalentClass` for cross-ontology alignment.

Every mapping needs a justification and a confidence. There is no SSSOM justification
value for "an LLM proposed this" — use `semapv:UnspecifiedMatching` and record the
model in `mapping_tool`.

## 6. Discipline

- **Evidence or nothing.** A proposal must cite measurement IRIs already in the graph.
  If you cannot anchor a term to something that survived extraction and validation, do
  not propose it — say the evidence is missing.
- **Never write to `schema/`.** It is outside the workspace and the policy refuses it.
  Proposals are staged; a human merges them.
- **Check before proposing.** Use `sparql_query` for what the graph supports and
  `read_file` on `experiments/results/ontology_conventions.json` for the measured tiers.
- **A gate passing is not correctness.** The checks prove a proposal is well-formed and
  logically compatible with the asserted axioms. They cannot tell you the term is
  scientifically right. Say what you are unsure about.

See `references/echo-conventions.md` and `references/h2kg-term-shape.md` for the
worked term templates.
