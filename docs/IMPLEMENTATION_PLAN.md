# AutoReach Implementation Plan

> Phased plan from "today" → "first paying customer" → "platform-ready engine."
> This is a living document. Each phase's success criteria must be met before the next phase begins.

## Phase 0 — Foundation reset (Days 1–3)

**Goal:** repo is clean, codebase is honest about its new shape, no legacy clutter blocking the next 6 months of work.

- [x] Tighten `.gitignore` (this commit)
- [x] Capture platform thesis in `docs/PLATFORM.md`
- [x] Capture phased plan in `docs/IMPLEMENTATION_PLAN.md`
- [x] Create `engine/` package skeleton with core abstractions as Python `Protocol` classes
- [ ] Move legacy CLI artefacts out of the way: archive `bulk_mail_with_attachment.py`, `cli_pro.py`, `quick_cli.py`, `q`, `run_send.sh`, `run_live_campaign.sh` into `legacy/` (keep for reference, exclude from imports)
- [ ] Move `app/` (the SaaS Flask shell) onto a `archive/saas-shell` branch — we may revive parts later, but it's not on the critical path for OaaS
- [ ] Rotate Google OAuth client secret in Google Cloud Console (manual, founder action)
- [ ] First commit on the new direction: `feat: pivot to platform engine + OaaS wedge`

**Exit criteria:** repo root contains only files relevant to the new direction. `engine/` package exists with documented protocol surface. Old code is preserved (legacy/) but not on the import path.

## Phase 1 — Engine v0 (Days 4–10)

**Goal:** the engine can run *one* outbound Job end-to-end, programmatically, observably, with the new abstractions — using the existing Gmail send code as the first adapter implementation.

- [ ] Implement `engine/core/types.py` — concrete dataclasses for Engagement, Agent, Job, Event, CostEntry
- [ ] Implement `engine/core/state.py` — Job state machine with explicit transitions and guards
- [ ] Implement `engine/core/store.py` — pluggable storage (start with SQLite + SQLAlchemy, share schema with future Postgres)
- [ ] Implement `engine/core/eventbus.py` — append-only event log with subscribers
- [ ] Implement `engine/core/ledger.py` — per-Engagement cost tracking
- [ ] Implement `engine/adapters/email_gmail.py` — wraps existing Gmail OAuth + MIME build code from `app/worker.py` behind the Adapter protocol
- [ ] Implement `engine/agents/outbound_agent.py` — first concrete Agent: given an Engagement + a prospect list, drives Jobs through the state machine
- [ ] Write integration test: full Job lifecycle (pending → sent → awaiting_reply) on a single test prospect, with all events recorded

**Exit criteria:** `python -m engine run-job --engagement-id 1 --prospect-id 1` sends one email, records 5+ structured events, debits the cost ledger, and survives a kill+restart mid-flight (state machine resumes).

## Phase 2 — Operator cockpit (Days 11–17)

**Goal:** *you* can run the engine for one customer (yourself) without touching code daily.

- [ ] Build `cockpit/` — minimal internal admin surface (Streamlit or FastAPI + HTMX, no React)
- [ ] Engagement CRUD: create customer, set offer copy, set ICP definition, set calendar URL, set monthly meeting target
- [ ] Prospect ingestion: upload CSV → validated, deduped, attached to Engagement
- [ ] Live job feed: tail of events across all engagements (sent, replied, booked)
- [ ] Reply triage queue: each inbound reply, classified, with a draft response for human approval
- [ ] Booking pipeline: positive replies → AI-drafted reply with calendar link → human approval → send
- [ ] Per-engagement P&L: revenue (booked meetings × price) − costs (ledger). Live margin.

**Exit criteria:** the cockpit is the only surface you touch to operate one customer end-to-end for a full day, with no code changes required.

## Phase 3 — First paying customer (Days 18–30)

**Goal:** AutoReach (you) is a paying OaaS customer of itself. Real money, real meetings, real signal.

- [ ] Define the offer: "AI-powered outbound infrastructure for B2B founders. $500 per qualified booked meeting. Refund if no-show."
- [ ] Define the ICP: B2B SaaS founders, seed–series A, US/EU, 5–50 employees, currently doing outbound (or about to)
- [ ] Build the first prospect list manually (200 prospects) — by hand, the first time, to learn what good looks like
- [ ] Run the first batch through the engine. Approve every send. Approve every reply.
- [ ] Track: send rate, reply rate, positive reply rate, booked meeting rate. These are the leading indicators we'll watch forever.

**Exit criteria:** ≥ 3 booked meetings in 30 days from a 200-prospect list, with margin > 70% (revenue > 3.3× variable cost).

## Phase 4 — Customer #2 and #3 (Days 31–60)

**Goal:** prove the engine generalizes. Each new customer must be onboardable in < 4 hours of operator time.

- [ ] Find 2 paying customers from your network (VIT alumni B2B founders, Outlier connections, IndieHackers)
- [ ] Onboard each via the cockpit only. Document every gap that required code.
- [ ] After each customer, ask: "what did I do manually that should be automated for customer #4?"
- [ ] Refactor the top 3 manual-pain items into engine features

**Exit criteria:** customer #3 is onboarded in < 4 hours. ≥ 10 booked meetings/month total across customers.

## Phase 5 — Engine hardening (Days 61–90)

**Goal:** the engine survives 10× scale and starts looking like a platform.

- [ ] Postgres + Redis + Celery wiring (reuse existing AutoReach infra here — it already works)
- [ ] Multi-tenant isolation tests: 10 simultaneous engagements, no cross-talk
- [ ] Deliverability monitoring: Postmaster integration, automatic pause on spam-rate breach
- [ ] HITL trust ramp: per-Engagement, first 50 sends require approval, then auto-send unlocks (kills the 11x-style trust collapse)
- [ ] Adapter SDK v0.1: write a second adapter (LinkedIn or Cal.com) to validate the protocol generalizes

**Exit criteria:** internal "AutoReach platform v0.1" passes all integration tests. We could give the SDK to a friendly developer and they could write a third adapter without our help.

## Phase 6 — Platform alpha (Days 91–180)

**Goal:** 5 design partners using the engine to build their own agents.

- [ ] Document the SDK publicly (docs site)
- [ ] Recruit 5 design partners from your engineering network (each builds one agent on top of the engine)
- [ ] Free during alpha — feedback is the price
- [ ] Watch which abstractions they break, fix them

**Exit criteria:** 5 design-partner agents in production. ≥ 3 of them generating meaningful action volume.

---

## Phase tracking

Update this table at the end of each phase. Honest assessments only.

| Phase | Started | Completed | Outcome | Lessons |
|---|---|---|---|---|
| 0 | TBD | — | — | — |
| 1 | — | — | — | — |
| 2 | — | — | — | — |
| 3 | — | — | — | — |
| 4 | — | — | — | — |
| 5 | — | — | — | — |
| 6 | — | — | — | — |
