# T03 — confirm constitution + add LICENSE

## Why
Confirm CLAUDE.md is present and intact (this is the agent's constitution and must never silently drift), and add a LICENSE file so the repo is properly attributable for thesis defence.

## Input state
- T02 merged.
- `CLAUDE.md` exists at repo root with the four Karpathy principles plus project-specific rules.
- No LICENSE file yet.

## Output state
- `CLAUDE.md` is unchanged from the version provided at project bootstrap. Confirm by checking:
  - It contains the heading `## 1. Think before coding`.
  - It contains the heading `## 2. Simplicity first`.
  - It contains the heading `## 3. Surgical changes`.
  - It contains the heading `## 4. Goal-driven execution`.
  - It contains the line `### Anti-patterns — refuse on sight`.
  - It contains the line `### Budget — €50 hard cap`.
- File `LICENSE` exists at repo root with the MIT license text, copyright `Copyright (c) 2026 Rahat <last name>`.
- File `AUTHORS.md` exists with one line: `Rahat <last name>, RWTH Aachen, Group G03 Earth`.

## Verification
```bash
grep -c "Think before coding" CLAUDE.md          # must print 1
grep -c "Simplicity first" CLAUDE.md             # must print 1
grep -c "Surgical changes" CLAUDE.md             # must print 1
grep -c "Goal-driven execution" CLAUDE.md        # must print 1
grep -c "Anti-patterns — refuse on sight" CLAUDE.md  # must print 1
grep -c "€50 hard cap" CLAUDE.md                 # must print 1
test -f LICENSE && echo "LICENSE ok"
test -f AUTHORS.md && echo "AUTHORS ok"
```
Every command must succeed; final two must print `LICENSE ok` and `AUTHORS ok`.

## Will touch
- `LICENSE` (new)
- `AUTHORS.md` (new)

## Will NOT touch
- **`CLAUDE.md` — this task verifies it, does NOT edit it.**
- Any other file.

## Out of scope
- Refining CLAUDE.md (that requires a design conversation, not a task).
- Adding a CONTRIBUTING.md or CODE_OF_CONDUCT.md.

## Notes / references
- Use the standard MIT license text — copy from https://opensource.org/licenses/MIT verbatim, change only year and copyright holder.
- If `CLAUDE.md` doesn't pass the grep checks, STOP. Do not "fix" it. That's a sign the project bootstrap was incomplete — escalate to the design assistant.
