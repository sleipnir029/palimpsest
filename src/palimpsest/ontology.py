"""ontology iris — EMMO ECHO resolution + verified hash table.

Per palimpsest-v2-design.md Appendix E. The schema generator (T19) calls
emmo_iri() to resolve classes whose hash was not human-verified at design
time; KNOWN_IRIS holds the 8 hashes that WERE human-verified (used verbatim
in schema/palimpsest.yaml). Tests in tests/test_ontology.py guarantee both
families stay in sync with upstream EMMO.
"""
from __future__ import annotations

from functools import cache
from pathlib import Path

import httpx
from rdflib import OWL, RDFS, Graph

EMMO_ECHO = "https://w3id.org/emmo/domain/electrochemistry"
_CACHE = Path.home() / ".cache" / "palimpsest" / "echo.ttl"

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
    """Load the ECHO turtle into an rdflib Graph. Cached to disk on first call.

    Atomic write: a Ctrl-C mid-download leaves no truncated .ttl behind that
    would poison every future call with `rdflib.BadSyntax`.
    """
    if not _CACHE.exists():
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        resp = httpx.get(EMMO_ECHO, follow_redirects=True, timeout=60.0)
        resp.raise_for_status()
        tmp = _CACHE.with_suffix(".ttl.tmp")
        tmp.write_bytes(resp.content)
        tmp.replace(_CACHE)
    g = Graph()
    g.parse(_CACHE, format="ttl")
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
