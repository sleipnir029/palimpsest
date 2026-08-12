"""resolve EMMO ECHO IRIs against the live graph (cached at ~/.cache/palimpsest/echo.ttl).

Two decoupled families per T18 advisor review:
- hash-as-class: catches EMMO removing/renaming the IRI (real breaking change).
- label-resolution: catches EMMO renaming the human label (cosmetic change).
A green-on-first / red-on-second tells you immediately which mode failed.
"""
import hashlib

import pytest
from rdflib import DCTERMS, OWL, RDF, URIRef

from palimpsest.ontology import (
    ECHO_SHA256,
    EMMO_ECHO,
    H2KG_NS,
    H2KG_SHA256,
    H2KG_TTL_URL,
    KNOWN_IRIS,
    _CACHE,
    _H2KG_CACHE,
    _pinned,
    echo_graph,
    emmo_iri,
    h2kg_graph,
)

OVERPOTENTIAL_HASH = f"{EMMO_ECHO}#electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6"


@pytest.mark.slow
def test_overpotential_resolves_to_verified_hash():
    """T18 card: emmo_iri('Overpotential') returns the verified hash."""
    assert emmo_iri("Overpotential") == OVERPOTENTIAL_HASH


@pytest.mark.slow
@pytest.mark.parametrize("label,expected_iri", list(KNOWN_IRIS.items()))
def test_known_hashes_still_declared_as_class(label, expected_iri):
    """Every KNOWN_IRIS hash is still declared as an owl:Class in ECHO."""
    g = echo_graph()
    assert (URIRef(expected_iri), None, OWL.Class) in g, (
        f"{label}: hash {expected_iri} is not declared as owl:Class in ECHO"
    )


@pytest.mark.slow
@pytest.mark.parametrize("label", list(KNOWN_IRIS.keys()))
def test_known_labels_resolve(label):
    """Every KNOWN_IRIS key resolves via emmo_iri() to its hard-coded hash."""
    assert emmo_iri(label) == KNOWN_IRIS[label]


# T47: H2KG terms are cross-vocab skos:closeMatch links (h2kg:Property / h2kg:Parameter
# individuals), resolved as h2kg: CURIEs in the schema — NOT through ontology.py's ECHO hash
# table. The namespaces are distinct, and no ECHO hash entry may point into the h2kg namespace.
# (Note: some labels like "Overpotential" are BOTH ECHO classes and H2KG fragments, so this
# guard checks IRI *values*, not label strings.) Catches a future mistake of pasting an h2kg
# IRI into KNOWN_IRIS. (H2KG_NS is imported from palimpsest.ontology — T69.)


def test_no_h2kg_iri_in_echo_table():
    """KNOWN_IRIS is the ECHO hash table — an h2kg IRI must never be pasted into it."""
    assert not any(iri.startswith(H2KG_NS) for iri in KNOWN_IRIS.values())


# H2KG_TTL_URL + h2kg_graph live in palimpsest.ontology (T69) and are imported above.

# Each mapped fragment → its expected H2KG type local-name. h2kg:Property are measured
# outputs; h2kg:Parameter are simulation inputs (so exact_mappings would be wrong — these
# are individuals, ours are owl:Classes). Verified against the live TTL 2026-06-10.
H2KG_FRAGMENT_TYPES = {
    "TafelSlope": "Property",
    "MassActivity": "Property",
    "TurnoverFrequency": "Property",
    "Overpotential": "Property",
    "ElectrochemicallyActiveSurfaceArea": "Property",
    "ExchangeCurrentDensity": "Parameter",
    "ChargeTransferCoefficient": "Parameter",
}


@pytest.mark.slow
@pytest.mark.parametrize("frag,typ", list(H2KG_FRAGMENT_TYPES.items()))
def test_h2kg_fragment_resolves(frag, typ):
    """T47: each mapped h2kg fragment exists in the live ontology with its claimed type.

    Only this guard catches a WRONG fragment (an upstream rename or a CURIE typo) —
    the offline tests only prove internal consistency. If H2KG ships a new version
    that renames a term, this fails loudly and the close_mapping must be updated.
    """
    g = h2kg_graph()
    subj = URIRef(H2KG_NS + frag)
    assert (subj, RDF.type, URIRef(H2KG_NS + typ)) in g, (
        f"h2kg:{frag} is not declared as h2kg:{typ} in {H2KG_TTL_URL}"
    )


# T87 — the pin. Both upstreams are served from unversioned URLs and both have
# already drifted (ECHO 4273 -> 4302 owl:Class between 2026-06-01 and 2026-07-27).
# _pinned() verifies on every load, so these tests fail on drift rather than
# quietly re-measuring against a different ontology.


@pytest.mark.slow
@pytest.mark.parametrize(
    "loader,cache,digest",
    [(echo_graph, _CACHE, ECHO_SHA256), (h2kg_graph, _H2KG_CACHE, H2KG_SHA256)],
    ids=["echo", "h2kg"],
)
def test_pinned_artefact_matches_digest(loader, cache, digest):
    """The bytes actually parsed are the pinned bytes, not a stale cache."""
    loader()
    assert hashlib.sha256(cache.read_bytes()).hexdigest() == digest


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        pass


def test_pinned_refuses_a_digest_mismatch(tmp_path, monkeypatch):
    """A moved upstream must raise, never silently reshape downstream numbers.

    Offline-safe: the real fetch is stubbed, so this asserts the guard rather than
    the network.
    """
    monkeypatch.setattr(
        "palimpsest.ontology.httpx.get", lambda *a, **k: _FakeResponse(b"moved")
    )
    dest = tmp_path / "x.ttl"
    with pytest.raises(RuntimeError, match="digest mismatch"):
        _pinned("https://example.invalid/x.ttl", dest, "00" * 32, "FAKE")
    assert not dest.exists(), "unverified bytes must not be left behind as a cache"


def test_pinned_heals_a_stale_cache(tmp_path, monkeypatch):
    """The reason the digest is re-checked on every load, not just on download.

    A cache written under an earlier pin must be replaced, not trusted.
    """
    good = b"the pinned bytes"
    digest = hashlib.sha256(good).hexdigest()
    dest = tmp_path / "x.ttl"
    dest.write_bytes(b"bytes from an older pin")

    calls: list[str] = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return _FakeResponse(good)

    monkeypatch.setattr("palimpsest.ontology.httpx.get", fake_get)
    assert _pinned("https://example.invalid/x.ttl", dest, digest, "FAKE") == dest
    assert dest.read_bytes() == good
    assert len(calls) == 1, "should re-fetch exactly once"

    # A cache that already matches must not hit the network at all.
    assert _pinned("https://example.invalid/x.ttl", dest, digest, "FAKE") == dest
    assert len(calls) == 1


@pytest.mark.slow
def test_h2kg_base_does_not_import_echo():
    """H2KG declares EMMO/ECHO alignment in prose but imports neither.

    Load-bearing for the whole ontology-extension phase: the repo previously
    assumed "H2KG reuses EMMO ECHO, so aligning to H2KG also aligns to EMMO"
    (T71). It does not. The linkage is a handful of SKOS mapping triples across
    2,176 h2kg-namespace terms, so the two upstreams must be targeted separately.

    When AIMWORKS does add an import, this fails — which is the notification.
    """
    g = h2kg_graph()
    assert list(g.objects(None, OWL.imports)) == []
    assert (None, DCTERMS.references, URIRef("https://w3id.org/emmo")) in g, (
        "expected the prose-level dcterms:references anchor to EMMO"
    )
