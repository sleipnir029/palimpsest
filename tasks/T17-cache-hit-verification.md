# T17 — cache hit on second invocation

> **Naming note.** This card and `PROGRESS.md`'s "T17" lines refer to DIFFERENT work. PROGRESS's
> T17 is the **parser-set / sshd-retrofit / image-bump infrastructure** (olmOCR dropped, dots +
> paddle added, sshd in all images, three 0.2.x bumps, 5/5 pod-verified end-to-end on `:0.2.2`).
> THIS card — kept under the same number for git history — is the **cache-hit verification test**
> that runs AFTER T16. Both happen to share "T17" but they're separate bodies of work.

## Why
Prove the cache actually works. Critical for budget.

## Input state
- T16 merged. parse_with_cache works end-to-end.
- At least one paper has all 5 cached outputs from T16's live run (T17 5-parser set: docling,
  mineru, chandra, dots, paddle).

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
