"""resolve EMMO ECHO IRIs against the live graph (cached at ~/.cache/palimpsest/echo.ttl).

Two decoupled families per T18 advisor review:
- hash-as-class: catches EMMO removing/renaming the IRI (real breaking change).
- label-resolution: catches EMMO renaming the human label (cosmetic change).
A green-on-first / red-on-second tells you immediately which mode failed.
"""
import pytest
from rdflib import OWL, URIRef

from palimpsest.ontology import EMMO_ECHO, KNOWN_IRIS, _echo, emmo_iri

OVERPOTENTIAL_HASH = f"{EMMO_ECHO}#electrochemistry_1cd1d777_e67b_47eb_81f1_edac35d9f2c6"


@pytest.mark.slow
def test_overpotential_resolves_to_verified_hash():
    """T18 card: emmo_iri('Overpotential') returns the verified hash."""
    assert emmo_iri("Overpotential") == OVERPOTENTIAL_HASH


@pytest.mark.slow
@pytest.mark.parametrize("label,expected_iri", list(KNOWN_IRIS.items()))
def test_known_hashes_still_declared_as_class(label, expected_iri):
    """Every KNOWN_IRIS hash is still declared as an owl:Class in ECHO."""
    g = _echo()
    assert (URIRef(expected_iri), None, OWL.Class) in g, (
        f"{label}: hash {expected_iri} is not declared as owl:Class in ECHO"
    )


@pytest.mark.slow
@pytest.mark.parametrize("label", list(KNOWN_IRIS.keys()))
def test_known_labels_resolve(label):
    """Every KNOWN_IRIS key resolves via emmo_iri() to its hard-coded hash."""
    assert emmo_iri(label) == KNOWN_IRIS[label]
