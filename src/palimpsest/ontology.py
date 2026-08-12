"""ontology iris — EMMO ECHO resolution + verified hash table.

Per palimpsest-v2-design.md Appendix E. The schema generator (T19) calls
emmo_iri() to resolve classes whose hash was not human-verified at design
time; KNOWN_IRIS holds the 8 hashes that WERE human-verified (used verbatim
in schema/palimpsest.yaml). Tests in tests/test_ontology.py guarantee both
families stay in sync with upstream EMMO.
"""
from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path

import httpx
from rdflib import OWL, RDFS, Graph, URIRef

EMMO_ECHO = "https://w3id.org/emmo/domain/electrochemistry"
_CACHE = Path.home() / ".cache" / "palimpsest" / "echo.ttl"

# H2KG (T47): the bare release IRI does not resolve (re-verified 2026-07-27:
# https://w3id.org/h2kg/hydrogen-ontology/releases/1.0.0 still 404s). T87 moves
# off the @main branch file onto the published ODK *base* artefact — base, not
# full, because base carries only the axioms H2KG itself asserts, which is what
# an alignment or an extension proposal targets.
H2KG_NS = "https://w3id.org/h2kg/hydrogen-ontology#"
H2KG_TTL_URL = "https://vimilabs.github.io/AIMWORKS/odk/artifacts/base.ttl"
_H2KG_CACHE = Path.home() / ".cache" / "palimpsest" / "h2kg_base.ttl"

# Pinned digests (T87). Both upstreams are moving targets served from unversioned
# URLs, and both have already drifted: ECHO grew 4273 -> 4302 owl:Class between
# 2026-06-01 and 2026-07-27, and H2KG's released base.ttl differs from the @main
# core_schema.ttl this module used to fetch. Without a pin, every measured number
# silently reshapes itself under the next upstream build.
#
# Bumping a digest is a deliberate act, not a chore: re-run tests/test_ontology.py
# and re-run any experiment whose numbers appear in the write-up.
ECHO_SHA256 = "27acb504e1e2453e30a3799ba5283ca2934b8c95b931440ec9806c9baef2fb14"
H2KG_SHA256 = "2cd2eb1c1956f2fd77aeb83ce4b5806f167d84b3bfdb854d8802c80527ae9e2f"


def _pinned(url: str, dest: Path, sha256: str, label: str) -> Path:
    """Fetch `url` into `dest`, guaranteeing its content digest is `sha256`.

    Verifies on every load, not just on download. A cache written under an
    earlier pin — or truncated by a Ctrl-C — is otherwise indistinguishable
    from a good one, and would keep passing tests while quietly serving stale
    axioms. A mismatched cache is re-fetched once; if the fresh copy still
    mismatches, upstream genuinely moved and that must fail loudly.

    Atomic write: a crash mid-download leaves no truncated .ttl behind that
    would poison every future call with `rdflib.BadSyntax`.
    """
    def digest() -> str | None:
        return hashlib.sha256(dest.read_bytes()).hexdigest() if dest.exists() else None

    if digest() != sha256:
        dest.parent.mkdir(parents=True, exist_ok=True)
        resp = httpx.get(url, follow_redirects=True, timeout=60.0)
        resp.raise_for_status()
        tmp = dest.with_name(dest.name + ".tmp")
        tmp.write_bytes(resp.content)
        tmp.replace(dest)

    actual = digest()
    if actual == sha256:
        return dest

    # Don't leave unverified bytes where the next call would treat them as a cache
    # and skip straight to re-downloading 4.6 MB before raising the same error.
    dest.unlink(missing_ok=True)
    raise RuntimeError(
        f"{label} digest mismatch — upstream moved.\n"
        f"  url:      {url}\n"
        f"  expected: {sha256}\n"
        f"  actual:   {actual}\n"
        f"Review the new release, then bump the pin in {__file__}."
    )

# Verified verbatim from palimpsest-v2-design.md Appendix E (lines 651-672).
# Each entry is regression-tested in tests/test_ontology.py against the live
# ECHO graph (hash-as-class AND label-resolution).
KNOWN_IRIS: dict[str, str] = {
    "Overpotential":             f"{EMMO_ECHO}#electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6",
    "ActivationOverpotential":   f"{EMMO_ECHO}#electrochemistry_7fa406b0_512a_4d59_9e0c_5d8aba0103ae",
    "AnodicOverpotential":       f"{EMMO_ECHO}#electrochemistry_565c0b10_70fe_441a_b76a_b9a8e08ca7b7",
    "ButlerVolmerEquation":      f"{EMMO_ECHO}#electrochemistry_d48ea516_5cac_4f86_bc88_21b6276c0938",
    "ChargeTransferCoefficient": f"{EMMO_ECHO}#electrochemistry_a4dfa5c1_55a9_4285_b71d_90cf6613ca31",
    "Electrocatalyst":           f"{EMMO_ECHO}#electrochemistry_a3b53904_22b1_42a9_a515_c8a3aed7e841",
    "AnodicReaction":            f"{EMMO_ECHO}#electrochemistry_a0580fa9_5073_44af_b33e_7adbc83892d0",
    "ElectrodeReaction":         f"{EMMO_ECHO}#electrochemistry_2e3e14f9_4cb8_45b2_908e_47eec893dec8",
}


@cache
def echo_graph() -> Graph:
    """Load the pinned ECHO turtle into an rdflib Graph, disk-cached."""
    g = Graph()
    g.parse(_pinned(EMMO_ECHO, _CACHE, ECHO_SHA256, "EMMO ECHO"), format="ttl")
    return g


@cache
def emmo_iri(class_label: str) -> str | None:
    """Resolve an EMMO ECHO class by its rdfs:label. Returns full IRI or None.

    Raises ValueError if the label resolves to more than one owl:Class — ECHO
    has 16 duplicate-label classes (e.g. "Powder", "C", "Grinding") that would
    otherwise return non-deterministic IRIs.
    """
    g = echo_graph()
    matches = [
        str(s) for s, _, o in g.triples((None, RDFS.label, None))
        if str(o) == class_label and (s, None, OWL.Class) in g
    ]
    if len(matches) > 1:
        raise ValueError(f"ambiguous label {class_label!r}: {matches}")
    return matches[0] if matches else None


def echo_iri_exists(iri: str) -> bool:
    """True if `iri` is declared as an owl:Class in ECHO.

    The skill-consistency gate (T69) resolves `emmo:` hash IRIs taken verbatim
    from the schema (class_uri / close_mappings); emmo_iri() resolves by label,
    so it can't answer this. Catches a typo'd or upstream-removed ECHO hash.
    """
    return (URIRef(iri), None, OWL.Class) in echo_graph()


@cache
def h2kg_graph() -> Graph:
    """Load the pinned H2KG base artefact into an rdflib Graph, disk-cached."""
    g = Graph()
    g.parse(_pinned(H2KG_TTL_URL, _H2KG_CACHE, H2KG_SHA256, "H2KG base"), format="ttl")
    return g


@cache
def h2kg_iri(fragment: str) -> str | None:
    """Resolve an H2KG term by local fragment. Returns the full IRI or None.

    A fragment "resolves" if it appears as a subject in the H2KG graph (it is a
    declared term). Mirrors emmo_iri()'s None-on-miss contract.
    """
    iri = URIRef(H2KG_NS + fragment)
    return str(iri) if (iri, None, None) in h2kg_graph() else None
