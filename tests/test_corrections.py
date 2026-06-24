"""WS1 — append-only superseding corrections (corrections.correct_measurement).

Covers the thesis-critical invariants:
- the correction captures the prior value and lands in a *named* graph;
- the ORIGINAL triple in the default graph is never mutated (append-only);
- a correction against an un-anchored / unknown measurement is refused (mirrors
  the pipeline's provenance-on-insert guard);
- an empty edit is refused;
- the correction is committed to git with the comment as title + body, and a
  human-diffable audit JSON is written.

PALIMPSEST_WORKSPACE is pointed at tmp_path so the git/audit side effects are
isolated from the real ./workspace.
"""

from __future__ import annotations

import json

import pytest

from schema.generated.pydantic import Evidence, Overpotential, Paper

from palimpsest.corrections import CorrectionError, correct_measurement
from palimpsest.store import PALIM, RDFStore

_PROV = "http://www.w3.org/ns/prov#"


def _seed(store: RDFStore) -> str:
    ev = Evidence(
        paper=Paper(sha256="abc123", title="A paper"),
        page=3, bbox_x0=0.1, bbox_y0=0.2, bbox_x1=0.3, bbox_y1=0.4,
        parser_name="docling", source_text="η = 2360 mV",
    )
    return store.insert_extraction(
        Overpotential(value=2360.0, unit_label="mV", evidence=ev), run_id="r1"
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("PALIMPSEST_WORKSPACE", str(tmp_path))
    return RDFStore()


def test_correction_is_append_only(store):
    iri = _seed(store)
    r = correct_measurement(
        store, measurement_iri=iri, author="human",
        comment="overpotential should be 236 not 2360", new_value=236.0, new_unit="mV",
    )
    assert r.prior_value == 2360.0
    assert r.prior_unit == "mV"
    assert r.paper_sha == "abc123"

    # Original triple untouched in the default (SHACL-validated) graph.
    orig = store.sparql(f"PREFIX palim: <{PALIM}> SELECT ?v WHERE {{ <{iri}> palim:value ?v . }}")
    assert float(orig[0]["v"]) == 2360.0

    # Superseding correction recorded in a named graph with full provenance.
    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> PREFIX prov: <{_PROV}> "
        "SELECT ?author ?prior ?corrected ?comment WHERE { GRAPH ?g { "
        f"?c prov:wasRevisionOf <{iri}> ; palim:correctionAuthor ?author ; "
        "palim:priorValue ?prior ; palim:correctedValue ?corrected ; "
        "palim:correctionComment ?comment . } }"
    )
    assert len(rows) == 1
    assert rows[0]["author"] == "human"
    assert float(rows[0]["prior"]) == 2360.0
    assert float(rows[0]["corrected"]) == 236.0
    assert "236" in rows[0]["comment"]


def test_refuses_unknown_measurement(store):
    _seed(store)
    with pytest.raises(CorrectionError, match="no provenance-anchored"):
        correct_measurement(
            store, measurement_iri=f"{PALIM}measurement/nonexistent",
            author="human", comment="x", new_value=1.0,
        )


def test_refuses_empty_edit(store):
    iri = _seed(store)
    with pytest.raises(CorrectionError, match="empty correction"):
        correct_measurement(store, measurement_iri=iri, author="human", comment="just a note")


def test_refuses_malformed_iri(store):
    # Untrusted input interpolated into SPARQL <...>: a malformed IRI must be a
    # handled CorrectionError, not a SyntaxError/ValueError 500 (review B1).
    _seed(store)
    with pytest.raises(CorrectionError, match="not a valid measurement IRI"):
        correct_measurement(
            store, measurement_iri="x> } junk #", author="human",
            comment="malformed", new_value=1.0,
        )


def test_multiple_corrections_accumulate(store):
    # The "accumulated corrections = labeled errors" claim for n>1: both persist,
    # each a distinct superseding node on the same measurement.
    iri = _seed(store)
    correct_measurement(store, measurement_iri=iri, author="human", comment="first", new_value=300.0)
    correct_measurement(store, measurement_iri=iri, author="palimpsest-agent", comment="second", new_value=236.0)
    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> PREFIX prov: <{_PROV}> "
        f"SELECT ?c ?corrected WHERE {{ GRAPH ?g {{ "
        f"?c prov:wasRevisionOf <{iri}> ; palim:correctedValue ?corrected . }} }}"
    )
    assert len(rows) == 2
    assert {float(r["corrected"]) for r in rows} == {300.0, 236.0}


def test_flag_wrong_records_correction(store):
    iri = _seed(store)
    correct_measurement(
        store, measurement_iri=iri, author="human",
        comment="not an overpotential", flagged_wrong=True,
    )
    rows = store.sparql(
        f"PREFIX palim: <{PALIM}> PREFIX prov: <{_PROV}> "
        f"SELECT ?f WHERE {{ GRAPH ?g {{ ?c prov:wasRevisionOf <{iri}> ; palim:flaggedWrong ?f . }} }}"
    )
    assert rows[0]["f"] == "true"


def test_correction_commits_title_body_and_audit(store, tmp_path):
    iri = _seed(store)
    r = correct_measurement(
        store, measurement_iri=iri, author="human",
        comment="wrong by 10x\nreviewer says 236 mV", new_value=236.0,
    )
    assert r.commit_sha

    from dulwich.repo import Repo
    msg = Repo(str(tmp_path))[r.commit_sha.encode()].message.decode()
    assert msg.startswith("correct: wrong by 10x")
    assert "reviewer says 236 mV" in msg  # full comment in the body

    rec = json.loads((tmp_path / "corrections" / f"{r.run_id}.json").read_text())
    assert rec["corrected_value"] == 236.0
    assert rec["prior_value"] == 2360.0
    assert rec["author"] == "human"


# --- agent tool contract (formatting + refusal branch), no disk store needed ----

def test_agent_tool_formats_result(monkeypatch):
    import palimpsest.corrections as corr_mod
    import palimpsest.store as store_mod
    from palimpsest.corrections import CorrectionResult
    from palimpsest.tools.correct_measurement import correct_measurement as tool

    monkeypatch.setattr(store_mod, "RDFStore", lambda *a, **k: object())
    monkeypatch.setattr(
        corr_mod, "correct_measurement",
        lambda store, **kw: CorrectionResult("c-iri", "run1", "abc", 2360.0, "mV", "deadbeefcafe"),
    )
    out = tool("m-iri", "fix it", new_value=236.0)
    assert "recorded correction c-iri" in out
    assert "prior=2360.0 mV" in out
    assert "commit deadbeef" in out


def test_agent_tool_refusal_branch(monkeypatch):
    import palimpsest.corrections as corr_mod
    import palimpsest.store as store_mod
    from palimpsest.corrections import CorrectionError
    from palimpsest.tools.correct_measurement import correct_measurement as tool

    monkeypatch.setattr(store_mod, "RDFStore", lambda *a, **k: object())

    def _raise(store, **kw):
        raise CorrectionError("not a valid measurement IRI: 'bad'")

    monkeypatch.setattr(corr_mod, "correct_measurement", _raise)
    out = tool("bad", "x", new_value=1.0)
    assert out.startswith("correction refused:")
    assert "not a valid measurement IRI" in out
