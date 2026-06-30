# Viewer breakage-fix — PAUSED (2026-06-24)

Status: **paused, not committed.** Code changes done + verified; one data decision open.

## Done (this session)
- `src/palimpsest/viewer/app.py` — added `_int()` / `_bbox()`; `_collect_triples` now uses them so one malformed `page`/`bbox` literal degrades to `None` instead of 500-ing `/data` or feeding the overlay a NaN box.
- `src/palimpsest/viewer/templates/viewer.html` — added `getJSON()` (throws on non-200); wrapped the PDF-render IIFE, matrix-loader IIFE, and `loadCell` in try/catch that render a readable error instead of freezing on "Loading…".
- `tests/test_viewer.py` — added `test_collect_triples_tolerates_bad_literals`.
- `.gitignore` — added `store.*/` (backup variants no longer clutter `git status`).
- **Data op:** swapped `store/` in-place with tightened-bbox content (`STORE_PATH` kept `"store"` → viewer/pipeline/corrections stay unified). Deleted redundant `store.tight/`, `store.pretight.bak/`, stale `store.bak/`. Kept `store.coarse.bak/`.

## Verified
- `pixi run pytest tests/test_viewer.py tests/test_viewer_matrix.py` → green (19, plus test_viewer_data = 24 total).
- Live browser: dots cell now draws a precise ~12×8px highlight (was unplaceable on coarse `store/`); cards render + scroll; induced 500 on `/pageinfo` shows "failed to load this cell — … HTTP 500" and recovers on next click.

## Root cause (corrected from initial guess)
Viewer was **not** universally broken — happy path worked. Real issue was **coarse bbox geometry** in `store/` (giant/unplaceable highlights). The no-error-handling freeze was a **latent** hole (no sub-fetch failed on the test paper). Both addressed.

## Open decision (BLOCKER to resume) — canonical store
Live `store/` has **603** measurements; `store.coarse.bak/` has **703** (independently confirmed; the 603 is a different/smaller extraction, not a re-tighten of the 703). No data lost — 703 set preserved in `store.coarse.bak/`. **Decide:** is 703 the latest full set (→ tighten it + swap in) or 603 (→ drop the 703 backup)?

## Independent review — residual items
- Misattribution corrected: the matrix UI + 4 routes + `test_viewer_matrix.py` are **pre-existing uncommitted work**, not this fix (session-start `git status` proves it). My 4 hunks held scope.
- No blocking code defects (XSS-safe, `None` bbox degrades cleanly, helpers sound).
- Valid kernels deferred: (a) at commit, separate breakage-fix from the pre-existing redesign / accurate message; (b) add a route-level degradation test (`/data` with a malformed literal → 200 + `None`); (c) optional `loadCell` rapid-click stale-content race (2-line `active`-token guard); (d) `_page_geometry` paddle branch unguarded `float()`.

## Resume checklist
1. Settle 603-vs-703 canonical store.
2. (opt) add route-level tolerance test + `loadCell` race guard.
3. Independent review of final diff, then commit — split fix vs redesign honestly.
