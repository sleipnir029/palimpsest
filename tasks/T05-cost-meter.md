# T05 — CostMeter + SQLite ledger + /budget live update

## Why
A hard €50 budget cap is non-negotiable. Every paid API or GPU call must check the meter first. The `/budget` command must update the cap live without restart.

## Input state
- T04 merged. AnthropicProvider works.
- `src/palimpsest/cost.py` is an empty stub.

## Output state
- File `src/palimpsest/cost.py` exports:
  - SQLite schema (DDL applied on first use): `cost_ledger(ts, kind CHECK IN ('llm','gpu'), provider, amount_eur, detail)` and `settings(key PRIMARY KEY, value)`. On first init, insert `('budget_eur', '50')` if not present.
  - Class `BudgetExceeded(Exception)` with attributes `spent`, `cap`, `projected`.
  - Class `CostMeter`:
    - `__init__(self, db_path: str = "palimpsest.db")` — opens connection, applies DDL, reads cap from settings.
    - `def cap(self) -> float` — property, reads live from settings table on every call.
    - `def soft(self) -> float` — returns `0.8 * cap`.
    - `def total_eur(self) -> float` — `SELECT COALESCE(SUM(amount_eur), 0) FROM cost_ledger`.
    - `def check_or_raise(self, projected_eur: float) -> None` — raises `BudgetExceeded` if `spent + projected > cap`.
    - `def record_llm(self, provider: str, eur: float, detail: str = "") -> None` — inserts ledger row.
    - `def record_gpu(self, eur: float, detail: str = "") -> None` — inserts ledger row.
    - `def set_budget(self, new_cap: int) -> str` — updates settings; returns status string. Refuses if `new_cap < spent`.
- File `tests/test_cost.py` covers: insert llm row, insert gpu row, total_eur, check_or_raise raises at cap, set_budget updates DB and is read by next `cap` call.

## Verification
```bash
pixi run pytest tests/test_cost.py -v
pixi run python -c "
from palimpsest.cost import CostMeter
import tempfile, os
db = tempfile.mktemp(suffix='.db')
m = CostMeter(db)
assert m.cap == 50.0
m.set_budget(75)
m2 = CostMeter(db)  # fresh instance to verify persistence
assert m2.cap == 75.0
print('persistence ok')
os.unlink(db)
"
```
Both must exit 0. Second must print `persistence ok`.

## Will touch
- `src/palimpsest/cost.py` (edit stub → full implementation)
- `tests/test_cost.py` (new)

## Will NOT touch
- Any other src file.
- `pixi.toml` (sqlite3 is in Python stdlib — no new deps).

## Out of scope
- Wiring CostMeter into providers → T06.
- The TUI cost dashboard → T28.
- The slash `/budget` command's chat-side wiring → T28.

## Notes / references
- Design ref: §F1 budget math; Appendix C SQL DDL; Appendix D slash command table.
- Use `sqlite3` from stdlib. Do NOT add sqlmodel or sqlalchemy.
- The `cap` property must re-read from DB every call so a concurrent `/budget` from the TUI takes effect for the next `check_or_raise`.
- Refuse to lower the cap below current spend — return a clear message.
