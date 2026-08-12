# H2KG term template

Loaded on demand with `read_file`, not injected into the prompt.

Measured over the pinned release artefact
`https://vimilabs.github.io/AIMWORKS/odk/artifacts/base.ttl`
(sha256 `2cd2eb1c…`, 19,852 triples, versionIRI 2026-07-11).

## What H2KG actually is

| | Count |
|---|---|
| `owl:Class` | 19 (an upper layer, not a term hierarchy) |
| `owl:NamedIndividual` | 3,249 total — **but see below** |
| — in the `h2kg:` namespace | **2,176 — this is the real term count** |
| — `file:///…/AIMWORKS/…` build stubs | 1,066 (ODK CI runner artefacts, `rdf:type` only) |
| — other namespaces | 7 |
| `owl:Restriction` | 0 |
| `rdfs:subClassOf` | 7 |
| `owl:imports` | **0** |
| SKOS mapping triples | 16 (0.7% of the 2,176 real terms) |
| ECHO classes reused directly | 1 |

**Cite 2,176, not 3,249.** A third of the individuals in the released artefact are
QuantityValue stubs the build pipeline emitted with `file:///home/runner/work/...`
IRIs — they are not terms, and quoting the raw count overstates the ontology by ~49%.

H2KG describes itself as having "conservative alignment to EMMO, ECHO, QUDT, ChEBI,
PROV-O". That alignment is `dcterms:references` — **prose, not logic**. Aligning to
H2KG does not align you to EMMO. Treat them as two independent targets.

Do not propose restrictions, disjointness, or hierarchy for H2KG. There is no
scaffolding to attach them to.

## Worked example — a new Property

```turtle
@prefix h2kg: <https://w3id.org/h2kg/hydrogen-ontology#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

h2kg:MassActivity
    a owl:NamedIndividual , h2kg:Property ;
    skos:prefLabel "Mass Activity"@en ;
    skos:altLabel "mass-normalised activity"@en , "MA"@en ;
    dcterms:description "A property denoting catalytic current per unit mass of active catalyst."@en ;
    h2kg:hasQuantityValue [ a qudt:QuantityValue ] .
```

Note the readable fragment — H2KG does **not** use opaque hash IRIs. Note also
`a owl:NamedIndividual , h2kg:<UpperClass>`: both types, always.

## Required, per type

Measured; the requirements genuinely differ by type, so a flat rule is wrong.

| Type | n | prefLabel | description | hasQuantityValue | altLabel |
|---|---|---|---|---|---|
| `Parameter` | 584 | 99.8% ✔ | 100% ✔ | 96.9% ✔ | 74.3% ~ |
| `Property` | 536 | 100% ✔ | 100% ✔ | 97.2% ✔ | 88.2% ✔ |
| `Matter` | 468 | 100% ✔ | 100% ✔ | 0.0% ✘ | 66.9% ~ |
| `Measurement` | 201 | 100% ✔ | 100% ✔ | 0.5% ✘ | 87.6% ✔ |
| `Instrument` | 192 | 100% ✔ | 100% ✔ | 0.0% ✘ | 76.0% ~ |
| `Manufacturing` | 131 | 100% ✔ | 100% ✔ | 0.0% ✘ | 87.8% ✔ |
| `Data` | 52 | 100% ✔ | 100% ✔ | 0.0% ✘ | 78.8% ~ |

✔ required · ~ advisory · ✘ do not emit

**Never emit** `h2kg:appliesToProfile` or `rdfs:isDefinedBy`: 0% and ≤0.2% respectively
across every type, despite appearing in the project's documentation.

## Choosing the upper class

The 13 domain-relevant classes: `Process`, `Matter`, `Property`, `Parameter`, `Data`,
`DataPoint`, `Agent`, `Instrument`, `Unit`, `Metadata`, `NormalizationBasis`,
`Measurement`, `Manufacturing`.

The decision that matters:

- **`Property`** — a measured output. Overpotential, Tafel slope, ECSA, mass activity.
- **`Parameter`** — a simulation or experimental input. Exchange current density and
  charge-transfer coefficient are `Parameter` in H2KG precisely because they are
  Butler–Volmer model inputs.

Getting this backwards is the most likely H2KG error, and it is not caught by any
syntactic check.

`NormalizationBasis` (6 individuals) is directly relevant to ECSA-normalised
quantities — check it before inventing a normalisation concept.

## Contribution channel

There is none. No `CONTRIBUTING.md`, no design-pattern docs, no PR workflow, and the
GitHub releases page is empty — releases ship via the docs site. The editing surface is
two source JSON-LD files fed through a 9-stage pipeline
(`quality → inspect → split → map → enrich → annotate → validate → docs → fair → release`).

Practically: contributing to H2KG is a conversation with the AIMWORKS team
(FZJ + KIT, Helmholtz HMC), not a pull request. Emit proposals as an SSSOM TSV and a
term-entry block; a human delivers them.
