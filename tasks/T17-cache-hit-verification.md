# T17 — cache hit on second invocation

## Why
Prove the cache actually works. Critical for budget.

## Input state
- T16 merged. parse_with_cache works end-to-end.
- At least one paper has all 4 cached outputs from T16's live run.

## Output state
- File `tests/test_cache_hit.py` covers:
  - Call `parse_with_cache([sample_pdf], cost_meter, cache)` once (assume already cached from T16; if not, do it here).
  - Read the cost ledger total before second call.
  - Call `parse_with_cache([sample_pdf], cost_meter, cache)` again.
  - Read the cost ledger total after.
  - Assert before == after (no new GPU charges).
  - Mock `RunPodSession.__enter__` to fail loudly if called. Test passes only if the second call NEVER instantiates RunPodSession.

## Verification
```bash
pixi run pytest tests/test_cache_hit.py -v -s
```
Test passes; output prints "second call used cache".

## Will touch
- `tests/test_cache_hit.py` (new)

## Will NOT touch
- Any src file. This task only adds a test.

## Out of scope
- Anything else.

## Notes / references
- This task should take 30 minutes — it's mostly a thinking task: how do you prove a function did NOT do something? Answer: patch the thing it would do and assert the patch never fires.
