"""Bring-your-own-agent extraction: prompt out, answer in, same gates + provenance.

Uses the bundled CC BY sample paper and its shipped docling parse (cache/), no LLM.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from palimpsest.external import ingest, render_prompt
from palimpsest.store import RDFStore

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"
_SHIPPED = Path("cache/3432d04920eb6649d15d8883e64dc7f3d54700ecd5050d09e31ae286f1d4f53d/docling.json")

pytestmark = pytest.mark.skipif(not _SHIPPED.exists(), reason="shipped docling cache absent")


def _span_id(prompt: str, needle: str) -> int:
    for line in prompt.splitlines():
        m = re.match(r"\[(\d+)\] \(p\d+\) (.*)", line)
        if m and needle in m.group(2):
            return int(m.group(1))
    raise AssertionError(f"no span containing {needle!r}")


def test_prompt_carries_skill_schema_and_numbered_spans():
    prompt = render_prompt(FIXTURE, parser_name="docling")
    assert "Numbered text spans" in prompt
    assert "Overpotential" in prompt  # schema class shown to the extractor
    assert _span_id(prompt, "236") >= 0


def test_ingest_runs_gates_and_inserts_with_provenance(tmp_path):
    prompt = render_prompt(FIXTURE, parser_name="docling")
    sid = _span_id(prompt, "236")
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({"items": [
        {"type": "Overpotential", "value": 236.0, "unit_label": "mV", "evidence": {"spans": [sid]}},
        # cites a span that does not contain the digits → must be dropped by the gate
        {"type": "Overpotential", "value": 999.0, "unit_label": "mV", "evidence": {"spans": [sid]}},
    ]}))
    store = RDFStore()

    summary = ingest(FIXTURE, answer, parser_name="docling", store=store,
                     db_path=str(tmp_path / "p.db"))

    assert summary["n_inserted"] == 1
    rows = list(store._store.query(
        "PREFIX prov: <http://www.w3.org/ns/prov#> "
        "SELECT ?m WHERE { { ?m prov:hadPrimarySource ?p } UNION "
        "{ GRAPH ?g { ?m prov:hadPrimarySource ?p } } }"))
    assert len(rows) >= 1
