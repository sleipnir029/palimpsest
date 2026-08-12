# ECHO term template

Loaded on demand with `read_file`, not injected into the prompt.

All rates below are from `experiments/results/ontology_conventions.json`, measured over
the **927 ECHO-local `owl:Class`** in the pinned artefact — not the 4,302 classes in the
merged closure, which include EMMO core and chemical-substance and follow different
conventions.

## Worked example — a new quantity

```turtle
@prefix echo: <https://w3id.org/emmo/domain/electrochemistry#> .
@prefix emmo: <https://w3id.org/emmo#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

echo:electrochemistry_3f2a91c4_8d17_4e0b_9a55_1c7ee0b4d2f9
    a owl:Class ;
    rdfs:label "MassActivity"@en ;
    skos:prefLabel "MassActivity"@en ;
    skos:altLabel "mass-normalised activity"@en ;
    # elucidation, NOT definition — this is a bridge to reality, not a formal
    # necessary-and-sufficient condition.
    emmo:EMMO_967080e5_2f42_4eb2_a3a9_c58143e835f9
        "Quotient of the catalytic current and the mass of the active catalyst material."@en ;
    # dual parent: dimensional (fixes the unit) + domain (places it in electrochemistry)
    rdfs:subClassOf echo:<dimensional-parent> ,
                    echo:<domain-parent> .
```

## Required, with measured base rates

Presence, over the 927 ECHO-local classes:

| Predicate | Present | Note |
|---|---|---|
| `skos:prefLabel` | 100.0% | exactly one (927/927); CamelCase for classes |
| `rdfs:label` | 100.0% | exactly one |
| any description | 100.0% | `elucidation` **or** `definition` **or** `conceptualisation` |
| `rdfs:subClassOf` | 100.0% | at least one; quantities take two (see below) |
| `elucidation` specifically | 99.9% | the usual choice |

Language tagging is measured separately and is **not** universal — do not conflate it
with presence:

| | `@en` on all values |
|---|---|
| `skos:prefLabel` | 90.5% (88 of 927 carry a plain literal) |
| `elucidation` | 99.8% |

Tag your own `@en`. The gate treats a missing tag as a defect even though upstream is
not fully consistent about it.

`elucidation` IRI: `https://w3id.org/emmo#EMMO_967080e5_2f42_4eb2_a3a9_c58143e835f9`

## Not required — despite the prose docs

| Predicate | Rate on ECHO-local | Note |
|---|---|---|
| any external definition source | 26.8% | cite when you have it; not mandatory |
| `skos:altLabel` | 32.5% | advisory |
| `IEVReference` | 17.8% | |
| `hasIUPACName` | **0.0%** | lives in EMMO core, not ECHO |
| `ISO80000Reference` | **0.0%** | lives in EMMO core |
| `qudtReference` | **0.0%** | lives in EMMO core |

The "ECHO requires IUPAC-sourced definitions" claim appears in EMMO's documentation and
is not borne out by the artefact. Do not fabricate a citation to satisfy it.

## IRI minting

Pattern, 99.5% conformant:

```
electrochemistry_[0-9a-f]{8}(_[0-9a-f]{4}){3}_[0-9a-f]{12}
```

A fresh UUID4 with hyphens replaced by underscores, in ECHO's own namespace. IRIs are
permanent — terms are **deprecated**, never deleted or renumbered.

## The dual-parent rule for quantities

Verified in the wild, on terms this schema already anchors:

| Term | dimensional parent | domain parent |
|---|---|---|
| `Overpotential` | `ElectricPotential` | `ElectrochemicalQuantity` |
| `ElectrodePotential` | `ElectricPotential` | `ElectrochemicalQuantity` |
| `ExchangeCurrentDensity` | `ElectricCurrentDensity` | `ElectrochemicalKineticQuantity` |
| `ChargeTransferCoefficient` | `RatioQuantity` | `ElectrochemicalKineticQuantity` |

The dimensional parent fixes the physical dimension and therefore the admissible unit;
the domain parent places the term in electrochemistry. Both are required.

`emmocheck`'s `test_quantity_dimension` / `test_physical_quantity_dimension` exist to
enforce the dimensional half. A quantity with only a domain parent fails.

## What upstream actually checks

ECHO's CI (`.github/workflows/validation.yml`) runs on every PR:

1. `emmocheck` — from EMMOntoPy. Relevant tests: `test_unique_labels`,
   `test_number_of_labels` (exactly one `prefLabel`), `test_number_of_rdfslabels`,
   `test_class_label` (CamelCase), `test_description` (any of the three),
   `test_quantity_dimension`, `test_namespace`.
2. an OWL reasoner check.

ECHO's `emmocheck_config.yml` skips `test_namespace` and `test_dimensional_unit`, and
exempts the abstract quantity superclasses (`ElectrochemicalQuantity`,
`…KineticQuantity`, `…TransportQuantity`, `…ThermodynamicQuantity`,
`ElectrochemicalConstant`, `ReactionRateConstant`) from `test_quantity_dimension`.
Mirror those skips so results are comparable to upstream.

## Submission ritual

Issue first, using the `request-new-term` template → branch `feature/<desc>` from
`dev` → PR **to `dev`** → commit message `[feature] … (#issue)`. New terms that do not
change an existing `prefLabel` or IRI are a **patch** bump.
