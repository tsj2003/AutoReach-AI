# Claude Prompt — Loop Engineering: Finish Moat + Phase 0→2

> **Paste this entire file into Claude Code** in the AutoReach-AI repo.
> Claude must run as a **Ralph / single-flow loop**: one user story per iteration, verify, mark pass, next story — until the PRD is done.

---

## COPY EVERYTHING BELOW THIS LINE INTO CLAUDE

---

# YOU ARE A LOOP ENGINEER

You are Claude Code inside **Attainly** (`/Users/tarandeepsinghjuneja/AutoReach-AI`).

You will complete the remaining product work using **loop engineering** (Ralph-style):

```
WHILE unpassed stories remain:
  1. Pick lowest-priority story with passes=false
  2. Implement ONLY that story
  3. Verify acceptance criteria (tests / build)
  4. Mark passes=true + note in prd + task tracker
  5. Commit on the feature branch (message: "US-XXX: <title>")
  6. Report chunk format
  7. Immediately start the NEXT story (do not wait for human unless blocked)
```

**Law:** `CLAUDE.md` wins over this prompt on tenant isolation, HITL, deliverability, secrets, honesty.

**Out of scope forever in this loop:** cold Instagram / Facebook / WhatsApp automation, Meta Ads platform, fake live intent radar.

---

# SOURCE OF TRUTH FOR THE LOOP

| File | Role |
|---|---|
| `.ralph/prd-moat-loop.json` | **Master backlog** — user stories US-001…US-015 |
| `docs/plans/task-moat-loop.md` | Live status table (update every story) |
| `CLAUDE.md` | Invariants |
| Branch `feat/signal-stack-e2e` | Stay here until US-015; then ask before merge |

**Do not invent new mega-features.** Only execute stories in the PRD. If a story is already done in code, verify criteria, mark `passes: true`, move on.

---

# ALREADY DONE (DO NOT REBUILD)

On `feat/signal-stack-e2e`:
- `min_signal_stack` API + `POST .../signals/simulate` + memory repository + evidence→personalizer/Guardian
- Tests for signal stack E2E; suite was green (~414)
- Founder set LLM API key in `.env` (never print/commit secrets)

Start at **US-001** unless audit proves it already passes.

---

# LOOP RULES (NON-NEGOTIABLE)

1. **One story per iteration.** If you cannot finish in one context window, the story was too big — split it in the PRD and continue with the smaller piece. Never leave half-wired stories marked passed.
2. **Acceptance criteria are binary.** Every criterion must be checkable. Run the tests named/implied. For UI stories: `npm --prefix dashboard run build` at minimum.
3. **Update trackers before starting the next story:**
   - Set `"passes": true` in `.ralph/prd-moat-loop.json` for the finished story
   - Update row in `docs/plans/task-moat-loop.md`
4. **Commit after each passed story** on `feat/signal-stack-e2e`:
   - `git add` only relevant files
   - `git commit -m "US-00X: <short title>"`
   - Do not push/merge unless founder asks
5. **Fail closed on secrets.** Never commit `.env`, tokens, credentials.
6. **Reuse outbox/jobs** for Actions — no parallel shadow system.
7. **After EVERY story, self-review:**
   - Spec compliance (criteria met?)
   - Quality (tenant scope, tests, no fake UI)
   - Then continue loop
8. **Stop only when:**
   - All stories `passes: true`, OR
   - Hard blocker (need secret/DNS/human decision) — report blocker clearly and wait
9. **North-star check after US-006:**
   UI demo path works: min_signal_stack=2 → simulate 1 (no prospect) → simulate 2 (evidence visible) → Actions shows Guardian + trace → approve path.

---

# STORY ORDER (EXECUTE IN THIS ORDER)

1. US-001 Actions API
2. US-002 Actions UI
3. US-003 Reasoning API fields
4. US-004 Reasoning UI
5. US-005 min_signal_stack + simulate in UI
6. US-006 LLM/template honest banner
7. US-007 Hard evidence gate (MOAT)
8. US-008 Reputation snapshot service (MOAT)
9. US-009 Reputation dashboard UI (MOAT)
10. US-010 Agency proof + deliverability (MOAT)
11. US-011 Reply Brain next actions
12. US-012 Tenant knowledge block
13. US-013 Scoped Autopilot
14. US-014 Soft/hard stop
15. US-015 Docs truth table

---

# PER-STORY EXECUTION TEMPLATE

```
### LOOP ITERATION: US-00X
1. Read story from prd-moat-loop.json
2. git status; confirm branch feat/signal-stack-e2e
3. Locate existing code (rg / read) — prefer extend over rewrite
4. Implement minimal change for THIS story only
5. Add/update tests
6. Run: focused pytest for touched area; dashboard build if UI
7. Spec review against acceptanceCriteria
8. Mark passes=true; update task-moat-loop.md
9. Commit US-00X
10. Report (format below)
11. START US-00(X+1) immediately
```

---

# REPORT FORMAT (EVERY ITERATION)

1. **Story:** US-00X — pass/fail
2. **Verdict:** Real / Prototype for what you touched
3. **Files changed**
4. **Tests/build run + results**
5. **PRD + task.md updated?** yes/no
6. **Commit hash** (if committed)
7. **Next story:** US-00Y starting now…

---

# PRODUCT POSITION (REMEMBER WHILE BUILDING)

> Attainly is the outbound system that won’t send unless the domain is healthy and the prospect has fresh, stacked buying evidence — then proves meetings and cost, not open rates.

Moat stories (US-007…010) must strengthen that sentence. If a change weakens it, reject the change.

---

# START NOW

1. Ensure `docs/plans/task-moat-loop.md` exists (create from template if missing).
2. Open `.ralph/prd-moat-loop.json`.
3. Audit US-001 against current outbox code — implement or mark passed.
4. Enter the loop and do not stop until US-015 passes or a hard blocker.

**BEGIN LOOP: US-001.**
