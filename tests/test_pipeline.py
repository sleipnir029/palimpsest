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
from palimpsest.runs import ExtractionRunLog
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
    # Inject a tmp run_log so the recorded run lands in a throwaway DB, not the
    # repo's palimpsest.db (run_paper's default target).
    run_log = ExtractionRunLog(str(tmp_path / "runs.db"))
    summary = run_paper(
        _PDF, store=store, cache=ParserCache(), cost_meter=meter,
        provider=_StubProvider(json.dumps({"items": []})), run_log=run_log,
    )
    assert summary == {
        "paper_sha": _SHA, "n_extracted": 0, "n_validated": 0, "n_inserted": 0,
    }
    assert len(store) == 0  # nothing inserted → empty graph


@needs_cache
def test_pipeline_records_extraction_run(tmp_path):
    """run_paper persists the run's counts (incl. the dropped `errors` count it
    used to discard) so a later read-only workspace_status (T57) can report them.
    """
    run_log = ExtractionRunLog(str(tmp_path / "runs.db"))
    summary = run_paper(
        _PDF, store=RDFStore(), cache=ParserCache(),
        cost_meter=CostMeter(str(tmp_path / "smoke.db")),
        provider=_StubProvider(json.dumps({"items": []})), run_log=run_log,
    )
    latest = run_log.latest_per_paper()
    assert summary["paper_sha"] in latest
    row = latest[summary["paper_sha"]]
    # Monotonic funnel recorded; the stub yields nothing so every count is 0.
    assert row["n_extracted"] == summary["n_extracted"] == 0
    assert row["n_inserted"] == summary["n_inserted"] == 0
    assert row["n_errors"] == 0
    assert row["parser_name"] == "mineru"  # run_paper's default parser


def test_run_paper_persists_drop_reasons(monkeypatch):
    """run_paper records the per-item drop REASONS (T58), one entry per stage:
    extract errors, SHACL drops, and insert refusals.

    Fully hermetic — parse/extract/validate are faked so the test controls
    exactly what drops at each stage, with no cache, LLM, or network.
    """
    import palimpsest.pipeline as pl

    class _M:  # stand-in measurement; only its class name is read for the reason
        pass

    class OverpotentialA(_M):
        pass

    class TafelSlopeB(_M):
        pass

    class MassActivityC(_M):
        pass

    a, b, c = OverpotentialA(), TafelSlopeB(), MassActivityC()

    monkeypatch.setattr(pl, "parse_with_cache", lambda pdfs, cm, cache: {"sha-x": {}})
    # extract: 3 Pydantic-valid instances + 2 pre-validation errors.
    monkeypatch.setattr(pl, "extract", lambda *a_, **k_: (
        [a, b, c],
        [(ValueError("value 236 not in cited span"), {"value": 236}),
         (ValueError("unit V != mV"), {"value": 1.7})],
    ))
    # SHACL: a ok, b fails (dropped), c ok.
    monkeypatch.setattr(pl, "validate_instance", lambda inst: (
        (True, "") if inst is not b else (False, "missing palimpsest:parserName")
    ))

    class _FakeStore:
        def insert_extraction(self, inst, *, run_id, parse_run_id=None, extraction_model=None):
            if inst is c:  # insert refusal on the last survivor
                raise ValueError("refuse to insert without Evidence")
            return "iri"

    class _FakeRunLog:
        def __init__(self):
            self.kw = None

        def record(self, **kw):
            self.kw = kw

    run_log = _FakeRunLog()
    summary = run_paper(
        "papers/x.pdf", store=_FakeStore(), cache=object(),
        cost_meter=object(), provider=object(), run_log=run_log,
    )

    # Return dict unchanged (T57 contract): 3 extracted, 2 validated, 1 inserted.
    assert summary == {
        "paper_sha": "sha-x", "n_extracted": 3, "n_validated": 2, "n_inserted": 1,
    }
    # Counts still recorded as before.
    assert run_log.kw["n_errors"] == 2
    # T58: reasons persisted, one per drop, tagged by stage.
    drops = json.loads(run_log.kw["errors_json"])
    by_stage = sorted((d["stage"], d["reason"]) for d in drops)
    assert by_stage == sorted([
        ("extract", "value 236 not in cited span"),
        ("extract", "unit V != mV"),
        ("shacl", "missing palimpsest:parserName"),
        ("insert", "refuse to insert without Evidence"),
    ])


def test_demo_cli_persists_to_disk_store(monkeypatch):
    """`demo <pdf>` must construct a path-backed RDFStore (the on-disk graph the
    viewer reads), not fall back to run_paper's discarded in-memory default.

    Guards the T30 persistence fix without LLM/network: run_paper + RDFStore are
    faked to record how the CLI calls them.
    """
    import sys

    import palimpsest.__main__ as cli

    captured: dict = {}

    class _FakeStore:
        def __init__(self, path=None):
            captured["path"] = path

    def _fake_run_paper(pdf, *args, store=None, **kw):
        captured["store"] = store
        return {"paper_sha": "x", "n_extracted": 0, "n_validated": 0, "n_inserted": 0}

    monkeypatch.setattr("palimpsest.store.RDFStore", _FakeStore)
    monkeypatch.setattr("palimpsest.pipeline.run_paper", _fake_run_paper)
    monkeypatch.setattr(sys, "argv", ["palimpsest", "demo", "papers/x.pdf"])

    cli.main()

    assert captured["path"] == "store"  # matches viewer.app.STORE_PATH
    assert isinstance(captured["store"], _FakeStore)  # explicit store, not None


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
