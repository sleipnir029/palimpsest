# SETUP.md — first 90 minutes

Follow this top-to-bottom. Do not skip steps. Do not work ahead.

## 0. Prerequisites (15 min)

You need:

- **macOS arm64** (M1 - being used)
- **Pixi** — install once: `curl -fsSL https://pixi.sh/install.sh | bash`. Confirm: `pixi --version`.
- **Git** — confirm: `git --version`.
- **Docker Desktop** (only needed for T10–T13, Dockerfile builds). Defer install until week 2 if you want.
- **An Anthropic API key** — get one at https://console.anthropic.com. Add $5 of credit to start. The Claude Code subscription you use to BUILD palimpsest does NOT pay for palimpsest's own API calls; this is a separate billing surface.
- **A RunPod account** (week 2 only) — sign up at https://runpod.io, add $5 of credit.

## 1. Drop this directory where you want it (5 min)

```bash
# pick a permanent home
mv ~/Downloads/palimpsest ~/projects/palimpsest
cd ~/projects/palimpsest
```

## 2. Initialize git and make the first commit (5 min)

```bash
git init
git add .
git commit -m "initial: project skeleton with CLAUDE.md, EXECUTION.md, 45 task cards"
```

## 3. Set up the .env file (5 min)

```bash
cat > .env <<EOF
ANTHROPIC_API_KEY=sk-ant-...your-key-here...
RUNPOD_API_KEY=                # add in week 2
EOF
echo ".env" >> .gitignore
git add .gitignore
git commit -m "chore: gitignore .env"
```

**Never commit .env.** If you do, rotate the key immediately.

## 4. Open Claude Code in this directory (5 min)

In Claude Code:

```
cd ~/projects/palimpsest
```

Open a fresh conversation. **Do not paste a long task description.** Instead, paste the **opening prompt** from `EXECUTION.md` Part 3:

```
You're working on palimpsest. Read these files in order and STOP:

1. CLAUDE.md
2. tasks/T73-hydrogen-demo-corpus-run.md
3. PROGRESS.md

After reading:
1. Restate the task in exactly 3 lines: input, output, verification.
2. List the files you will touch (and confirm they match the card).
3. List the files you will NOT touch.
4. Wait for my explicit "go" before writing any code.

Do not read palimpsest-v2-design.md unless I ask. Do not read other source files
unless the task card lists them. Do not run shell commands yet.
```

## 5. The first task cycle (45 min)

Claude will read the three files and produce a 3-line restatement. **Read it carefully.**

- If the restatement matches the task card → say `go`.
- If anything is off → say `re-read tasks/T01 — note that <specific clarification>` and ask for restatement again. Do this until clean.
- Never, ever proceed without a clean restatement.

When Claude finishes T01, paste the **closing checklist** from EXECUTION.md Part 3:

```
Before I review, complete this checklist literally:

1. Paste the verbatim output of: pixi install && pixi run python -c "import palimpsest; print('ok')"
2. Paste the verbatim output of: git diff --stat
3. Did you touch any file not on the "will touch" list in T01? If yes, list it.
4. Did you add any dependency not in the task spec? If yes, name it.
5. Did you write any code, even a one-liner, that doesn't directly satisfy T01? If yes, name it.
6. Did any test fail or get skipped? If yes, paste the failure.

Do not write a summary. Do not commit yet. Wait for my "merge".
```

Read every answer literally. Cross-check against T01. Then either `merge` (Claude commits + updates PROGRESS.md) or push back.

**Close the conversation when T01 is merged.** Each task gets a fresh conversation.

## 6. The first day (rest of the 90 min)

After T01 merges, repeat the cycle for T02 and T03:

- T02 — repo skeleton (30 min). Quick.
- T03 — initial commit confirmation (15 min). Almost trivial.

By end of day 1 you have a working pixi environment and a clean repo structure. **You have not written any real code yet.** That's correct. The foundation is the foundation.

## 7. End of every day

- `cat PROGRESS.md | tail -10` — confirm today's lines are accurate.
- Append to `DEVIATIONS.md` if anything surprised you.
- Glance at tomorrow's first task card; sleep on it.

## 8. End of every week

- `pixi run palimpsest cost report` — verify spend trajectory.
- `git tag week-N-done` — mark the week.
- Sunday: read EXECUTION.md again. Write next week's cards if they need refining.

## Common mistakes (avoid these)

1. **Reading palimpsest-v2-design.md every session.** Don't. It's a reference. The task card is your context.
2. **One long conversation across multiple tasks.** Don't. Each task = fresh conversation.
3. **Saying "looks good" without reading the diff.** Always `git diff --stat`. Always.
4. **Accepting "tests pass" without verbatim output.** Always paste-verbatim.
5. **Letting Claude add a "useful helper" not in the card.** Reject. File a future task if needed.
6. **Skipping the restatement step.** This is the single most expensive omission.
7. **Editing CLAUDE.md / EXECUTION.md / palimpsest-v2-design.md without a fresh design conversation.** Those are the constitution. Mutating them silently is how projects drift.

## What good looks like at end of week 1

- 8 commits in `git log`, one per task (T01–T08).
- 8 ✓ lines in PROGRESS.md.
- Cost ledger shows < €3 spent (mostly on T04 smoke test and T08 end-to-end).
- `pixi run python -m palimpsest "what is the title of papers/sample.pdf?"` returns the correct title.
- You feel slightly bored. **That's the goal.** Boring means the methodology is working.

If week 1 felt chaotic, re-read EXECUTION.md Part 12 before starting week 2.

---

You're set. Open tasks/T01-pixi-init.md and start.
