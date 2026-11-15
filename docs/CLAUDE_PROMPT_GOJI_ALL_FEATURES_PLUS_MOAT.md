# Claude Prompt — ALL Gojiberry Features + Attainly Exceptional Moat

> Paste into Claude Code in **AutoReach-AI**.
> Goal: make Attainly a **full AI GTM agent like [Gojiberry](https://gojiberry.ai/)** — then make it **exceptional** with our moat.
> Run as a **loop**: one PRD story per iteration until done.

---

## COPY EVERYTHING BELOW THIS LINE INTO CLAUDE

---

# MISSION

You are Claude Code inside **Attainly** (`/Users/tarandeepsinghjuneja/AutoReach-AI`).

Build Attainly into:

> **An AI GTM agent that does everything Gojiberry does for outbound —
> PLUS a moat Gojiberry does not own: deliverability-safe, evidence-gated, reputation-protected, ROI-provable execution.**

**Wrong goal:** clone Gojiberry’s marketing.
**Right goal:** **feature parity on the agent job**, then **win on trust** (domain survival + proof).

Obey **`CLAUDE.md`**. Tenant isolation, HITL, deliverability fail-safe, secrets, honesty always win.

---

# WHAT GOJIBERRY IS (CORRECT MODEL — NOT “LINKEDIN ONLY”)

Gojiberry ([gojiberry.ai](https://gojiberry.ai/)) is an **AI sales / GTM agent**:

1. Enter website → learns business, ICP, pitch
2. Finds & scores high-intent leads (buying + social signals, lookalikes, ICP filter)
3. Multichannel outreach: **email + socials** with AI personalized messages
4. Agent coordinates outreach (no heavy sequence building)
5. Full auto **or** approve-before-send (Copilot)
6. Unified inbox; replies pre-written and ready
7. Gets better every week; industry benchmarks
8. Enrichment waterfall; CRM / API / MCP
9. Replaces stack: lead finding + signals + copywriting + sequencing

You must implement **all of the above** into Attainly (see PRD).
You must **not** implement cold WhatsApp blasting or reckless Meta DM spam that burns accounts and destroys our “safe” brand. LinkedIn/social = **safe assisted or capped HITL path** (story GP-014).

---

# ATTAINLY EXCEPTIONAL MOAT (MUST SHIP — THIS IS WHY WE WIN)

These are **not optional extras**. They make Attainly exceptional vs Gojiberry:

| Moat | Product law |
|---|---|
| **Evidence gate** | Stacked campaigns cannot send without fresh cited buying signals |
| **Deliverability Guardian** | Pre-send spam/AI-fingerprint score; **block → always HITL** |
| **Reputation OS** | Mailbox health, caps, pause reasons; unhealthy = no send |
| **Proof pack** | COGS + meetings + margin + health + trace IDs (not vanity opens) |
| **Actions OS** | One operator inbox: approve/reject/snooze/edit/rerun + transparent reasoning |
| **Tenant walls** | Agency-safe isolation; no cross-client burn |

**Positioning line (use everywhere):**

> Gojiberry is the AI GTM agent that finds intent and runs email + social outreach.
> Attainly is that agent **plus** the system that won’t burn your domain: stacked evidence only, Guardian + reputation gates, human control, and proof of meetings vs cost.

If a feature increases volume but weakens the moat — **reject it** or put it behind hard gates.

---

# LOOP ENGINEERING

Source of truth:
- **PRD:** `.ralph/prd-goji-parity-moat.json` (GP-001 … GP-020)
- **Tracker:** `docs/plans/task-goji-parity-moat.md` (create if missing)
- **Branch:** create/use `feat/goji-parity-moat` (or continue current feature branch if already ahead — prefer one clean branch)

```
WHILE any story has passes=false:
  pick lowest priority
  implement ONLY that story
  verify acceptance criteria (tests / dashboard build for UI)
  set passes=true; update tracker
  commit: "GP-XXX: <title>"
  report
  immediately start next story
```

Stop only when all `passes: true` or hard blocker (secrets/DNS/human decision).

**Reuse** existing Signal Stack, website intake, Guardian, Outbox, Inbox, ledger, mailbox health. Extend; don’t rewrite the company.

**Already on `feat/signal-stack-e2e` (absorb, don’t redo):**
min_signal_stack, signals/simulate, evidence→personalizer/Guardian. Merge or cherry-pick into the parity branch as needed, then continue GP stories (mark GP-006/GP-016 passed if criteria already met after verify).

---

# FULL FEATURE MATRIX (BUILD ALL)

## A) Gojiberry parity (must exist in product)

| # | Gojiberry capability | Attainly story | Implementation note |
|---|---|---|---|
| 1 | Website → agent config | GP-001 | Intake + UI |
| 2 | Buying/social signals | GP-002 | Catalog + matrix |
| 3 | ICP-only prospects | GP-003 | Pre-filter gate |
| 4 | Smart lead scoring | GP-004 | Hybrid score + UI |
| 5 | Lookalikes | GP-005 | Seed → candidates → still gated |
| 6 | AI personalized messages | GP-006 | Evidence-grounded email |
| 7 | No heavy sequences / agent cadence | GP-007 | Auto follow-ups as jobs |
| 8 | Unified inbox | GP-008 | Unibox |
| 9 | Full auto or approve | GP-009 | Copilot / Autopilot |
| 10 | Reply drafts ready | GP-010 | Reply Brain |
| 11 | Learns weekly + benchmarks | GP-011 | Insights report |
| 12 | Email enrichment waterfall | GP-012 | Adapter + mock/real |
| 13 | CRM / API / MCP | GP-013 | Honest status |
| 14 | Socials (LinkedIn etc.) | GP-014 | **Safe** drafts/HITL/caps — not ban-bait |

## B) Exceptional moat (must exist — our edge)

| # | Moat | Story |
|---|---|---|
| 15 | Deliverability Guardian hard gate | GP-015 |
| 16 | Evidence-gated dispatch | GP-016 |
| 17 | Reputation OS dashboard | GP-017 |
| 18 | Proof pack (ROI + health + traces) | GP-018 |
| 19 | Actions List + reasoning panel | GP-019 |
| 20 | Docs + demo script (truthful) | GP-020 |

---

# HARD RULES

1. One story per iteration. Binary acceptance criteria.
2. Never commit secrets.
3. Never mark CRM/MCP/social “live” if Prototype.
4. Guardian block always beats Autopilot.
5. Empty signal matrix → create nothing.
6. Cold WhatsApp / cold IG-FB DM spray = **forbidden**.
7. LinkedIn/social must include safety limits + HITL path.
8. After each story: spec review + quality review → commit → next.
9. Prefer Firecrawl for website fetch if upgrading GP-001.
10. LLM keys may exist in `.env` — use them; never print them.

---

# NORTH-STAR DEMO (EXCEPTION PRODUCT)

A stranger can:

1. Paste website → agent config
2. Enable signal types + ICP + min_signal_stack=2
3. Ingest/simulate signals → scored prospect with evidence
4. See grounded email (+ optional LinkedIn draft)
5. See Guardian risk + reputation status
6. Approve in Actions (or Autopilot if enabled and safe)
7. Send via healthy mailbox
8. Reply → drafted next action in Unibox
9. Open Proof pack: cost, meeting, health, traces

That is **Gojiberry completeness + Attainly exceptionalism**.

---

# REPORT FORMAT (EVERY STORY)

1. Story GP-XXX — pass/fail
2. Goji parity feature advanced / Moat feature advanced
3. Real / Partial / Prototype
4. Files + tests/build
5. PRD + tracker updated?
6. Commit
7. Next story starting…

---

# START NOW

1. Create `docs/plans/task-goji-parity-moat.md` status table for GP-001…GP-020.
2. Ensure branch `feat/goji-parity-moat` (or merge signal-stack work into it).
3. Open `.ralph/prd-goji-parity-moat.json`.
4. Verify/absorb existing Signal Stack work into GP-006/GP-016.
5. **BEGIN LOOP: GP-001** and do not stop until GP-020 passes or hard blocker.

Build the full Gojiberry agent. Make the moat non-negotiable. Make Attainly exceptional.
