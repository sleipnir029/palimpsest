"""T05 tests. Pure SQLite, no network — runs offline and free."""

import pytest

from palimpsest.cost import _CANONICAL_DB, BudgetExceeded, CostMeter


def test_default_budget(tmp_path):
    m = CostMeter(str(tmp_path / "c.db"))
    assert m.cap == 50.0
    assert m.soft() == pytest.approx(40.0)
    assert m.total_eur() == 0.0


def test_record_and_total(tmp_path):
    m = CostMeter(str(tmp_path / "c.db"))
    m.record_llm("anthropic", 1.50, "extraction call")
    m.record_gpu(2.25, "runpod 4090 docling")
    assert m.total_eur() == pytest.approx(3.75)


def test_check_or_raise_at_cap(tmp_path):
    m = CostMeter(str(tmp_path / "c.db"))
    m.record_llm("anthropic", 49.0)
    m.check_or_raise(1.0)  # 49 + 1 == 50, not over cap → ok
    with pytest.raises(BudgetExceeded) as exc:
        m.check_or_raise(1.5)  # 49 + 1.5 > 50
    assert exc.value.spent == pytest.approx(49.0)
    assert exc.value.cap == 50.0
    assert exc.value.projected == pytest.approx(1.5)


def test_set_budget_persists(tmp_path):
    db = str(tmp_path / "c.db")
    m = CostMeter(db)
    assert m.set_budget(75) == "budget set to €75"
    m2 = CostMeter(db)  # fresh instance reads from disk
    assert m2.cap == 75.0


def test_set_budget_refuses_below_spend(tmp_path):
    m = CostMeter(str(tmp_path / "c.db"))
    m.record_gpu(30.0)
    msg = m.set_budget(20)
    assert msg.startswith("refused")
    assert m.cap == 50.0  # unchanged


def test_bare_db_name_redirects_to_canonical():
    # The €50 cap must be ONE ledger regardless of cwd: a bare relative "palimpsest.db"
    # (what every runtime call site passes) is redirected to the repo-root canonical file
    # so launching from a subdir can't fork an empty, under-counting ledger.
    assert CostMeter("palimpsest.db").db_path == _CANONICAL_DB


def test_absolute_path_is_not_redirected(tmp_path):
    # Tests (and any explicit absolute path) must pass through untouched.
    p = str(tmp_path / "x.db")
    assert CostMeter(p).db_path == p
