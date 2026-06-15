"""T25 — end-to-end pipeline tests: 1 paper → graph + SHACL pass.

Two tests:
  (a) offline smoke — stub provider returns no items; asserts the wiring
      (parse cache short-circuit → extract → validate → insert → summary) runs
      and yields all-zero counts. No network, no spend. Runs in CI.
  (b) live acceptance — real DeepSeek; asserts >=5 inserted, then a single
      correlated SPARQL query proves one Overpotential is BOTH within 10% of the
      236 mV ground truth AND carries a currentDensity condition (T46/C1 guard:
      conditions aren't stripped off the headline value). `--live`-gated.

Both gate on the sample paper's full 5-parser cache being present (gitignored);
a fresh or partial clone skips rather than spinning a paid pod.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from palimpsest.cache import ParserCache
from palimpsest.cost import CostMeter
from palimpsest.parsers.commands import PARSERS
from palimpsest.pipeline import run_paper
from palimpsest.providers.anthropic import LLMResponse
from palimpsest.store import PALIM, RDFStore, _class_iri
from schema.generated.pydantic import Overpotential

load_dotenv()

_PDF = Path("papers/s41467-022-35426-8.pdf")
_HITS = sorted(Path("cache").glob("*/mineru.json"))
_SHA_DIR = _HITS[0].parent if _HITS else None
_SHA = _SHA_DIR.name if _SHA_DIR else None
# Require ALL 5 parser outputs cached — that is what makes parse_with_cache
# short-circuit (no pod, no spend). A mineru-only cache would fall through to a
# paid pod run, so a partial cache must skip, not run.
_CACHED = bool(_HITS) and _PDF.exists() and all(
    any(_SHA_DIR.glob(f"{p}.*")) for p in PARSERS
)

needs_cache = pytest.mark.skipif(
    not _CACHED, reason="sample paper not cached; run T16 first"
)


class _StubProvider:
    """Returns a fixed LLMResponse for any input (mirrors test_extract)."""

    name = "stub"

    def __init__(self, response_text: str) -> None:
        self._text = response_text
        self.calls = 0

    def complete(self, system, messages, tools=None, cache_breakpoints=None):
        self.calls += 1
        return LLMResponse(
            text=self._text, tool_calls=[],
            usage={"input_tokens": 100, "output_tokens": 50,
                   "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            raw={},
        )


@needs_cache
def test_pipeline_wiring_empty_extraction(tmp_path):
    """Stub extraction yields nothing → pipeline runs end-to-end, counts are zero.

    Exercises the integration wiring (import graph, parse_with_cache short-circuit,
    summary dict keys) without the brittleness of stubbing span-cited content.
    """
    store = RDFStore()
    meter = CostMeter(str(tmp_path / "smoke.db"))
    summary = run_paper(
        _PDF, store=store, cache=ParserCache(), cost_meter=meter,
        provider=_StubProvider(json.dumps({"items": []})),
    )
    assert summary == {
        "paper_sha": _SHA, "n_extracted": 0, "n_validated": 0, "n_inserted": 0,
    }
    assert len(store) == 0  # nothing inserted → empty graph


@pytest.mark.live
@needs_cache
def test_pipeline_end_to_end_live(tmp_path):
    """Real DeepSeek run: >=5 inserted, value + condition retrievable via SPARQL."""
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")

    store = RDFStore()
    meter = CostMeter(str(tmp_path / "live.db"))
    summary = run_paper(_PDF, store=store, cost_meter=meter)
    print(f"\npipeline: {summary}, spend €{meter.total_eur():.4f}")
    assert summary["n_inserted"] >= 5, f"only {summary['n_inserted']} inserted"

    # Overpotential is typed with its EMMO ECHO IRI (not palimpsest:Overpotential);
    # resolve it via the store's own helper so the query stays in sync with store.py.
    # str(NamedNode) already renders the bracketed <IRI> form for SPARQL.
    ov = str(_class_iri(Overpotential.model_construct()))

    # T46/C1 guard: ONE correlated query binds value AND condition to the SAME ?m,
    # so it proves the ~236 mV Overpotential ITSELF kept its currentDensity. Two
    # independent queries would pass even if 236 lost its condition while some other
    # Overpotential kept one — exactly the condition-dropping regression to catch.
    rows = store.sparql(
        f"SELECT ?val ?cd WHERE {{ ?m a {ov} ; <{PALIM}value> ?val ; "
        f"<{PALIM}condition> ?c . ?c <{PALIM}currentDensity> ?cd }}"
    )
    assert any(abs(float(r["val"]) - 236.0) <= 23.6 for r in rows), (
        "no Overpotential ~236 mV (within 10%) that also retained a currentDensity "
        f"condition (C1 regression); got {[(r['val'], r['cd']) for r in rows]}"
    )
