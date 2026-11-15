# Claude Prompt — Merge FirstQuadrant + Gojiberry Into Attainly

> **How to use:** Open the `AutoReach-AI` repo in Claude Code (or paste this entire file as the first message). Claude must follow `CLAUDE.md` as law. This prompt is the mission.

---

## COPY EVERYTHING BELOW THIS LINE INTO CLAUDE

---

# MISSION

You are Claude Code inside **Attainly** (`/Users/tarandeepsinghjuneja/AutoReach-AI`, also known internally as AutoReach).

Your job is to **selectively absorb the best product DNA from two YC AI sales startups** — **FirstQuadrant** (sunset AI sales execution OS) and **Gojiberry** (active intent-based GTM agent) — and **implement the high-leverage pieces into Attainly**, without turning Attainly into a clone, a bloated kitchen sink, or a fake “autonomous agent” marketing toy.

**Read and obey `CLAUDE.md` first.** It is the operating charter. If anything in this prompt conflicts with `CLAUDE.md` invariants (tenant isolation, HITL, deliverability fail-safe, intent discipline, auditability, ROI ledger, secret hygiene, production truth), **`CLAUDE.md` wins**.

---

# PRODUCT TRUTH (do not invent a different company)

Attainly is an **AI revenue-operations and outbound-execution cockpit** for small B2B teams, founder-led sales, agencies, and service businesses.

**Moat (protect and deepen):**
trustworthy AI revenue execution = tenant isolation + human-in-the-loop + deliverability-aware dispatch + OpenTelemetry/OpenInference audit trails + intent-signal discipline (Signal Stack) + cost/outcome ledger + CRM sync + honest ROI proof.

**Not the moat:** “AI writes emails.” Everyone has that.

**Near-term goal (next 30 days):** pilot-ready demo loop:
`website intake → campaign + signal matrix → stacked signals → prospect → AI draft grounded in evidence → deliverability score → human approve → healthy mailbox send → reply classify → meeting → cost/ROI proof`

Do **not** chase “billion-dollar platform” features. Every feature must help win/keep a pilot, reduce risk, increase trust, make ROI visible, ease onboarding, or sharpen the demo.

---

# COMPETITOR DNA TO ABSORB (synthesized research)

## A) Gojiberry — steal the *top-of-funnel radar*

Steal ideas (map onto Attainly; do not copy brand/UI):

1. **Website → agent config in minutes** — already partially shipped as website intake (`engine/llm/website_intake.py`, Campaigns “Auto-fill from website”). Harden + make the demo path undeniable.
2. **Intent / buying / social signals as the lead source** — Attainly already has Signal Stack (`engine/intent/signal_stack.py`). **Wire it end-to-end**; this is the #1 product gap vs Gojiberry.
3. **ICP pre-filter before any outreach** — never message non-ICP.
4. **Hybrid scoring** — ICP fit + behavioral intent + freshness/decay + negative scoring.
5. **Signal-grounded personalization** — drafts must cite the actual triggers (Attainly already stores `research.signal_stack.evidence` — enforce this in personalizer + UI).
6. **Full auto OR approve-before-send** — map to Attainly HITL + scoped Autopilot (never silent autonomy).
7. **Weekly learning loop** — track what converts (signal types, subject angles, reply rates) and surface recommendations (not silent self-rewriting of brand voice).
8. **Lookalikes of best customers** — later phase; only after E2E signal ingest works.
9. **Unified inbox** — Attainly Inbox exists; make it the operational center for replies + next actions.
10. **MCP for CRM/tools** — contract exists (`engine/workflows/crm_sync.py`, `engine/integrations/mcp_gateway.py`) but is inert. Only finish if a real MCP path can be tested; otherwise keep labeled Prototype and do not fake it in UI.

**Do NOT prioritize yet (unless founder explicitly demands):** LinkedIn automation, Chrome extension, free marketing tools, “no sequences” marketing gimmicks that break deliverability control.

## B) FirstQuadrant — steal the *execution OS after the first touch*

Steal ideas:

1. **Actions List as next-best-action queue** — AI proposes: reply / follow-up / nurture / qualify / update deal / snooze. Human approves. Map onto Attainly Outbox + Inbox + Operations — don’t invent a second conflicting system.
2. **Brain-style context-aware reply handling** — classify inbound (positive / OOO / postpone / competitor / unsubscribe / meeting cancel) → draft next action with transparent reasoning.
3. **Autopilot scopes** — off by default; can enable per campaign / rule / nurture / suggested import. If multiple rules apply, autopilot only fires when all agree (FQ rule — adopt it).
4. **Fine-tuning as natural-language rules** — Email / Note / General / Knowledge — scoped to Views/Campaigns. Teach Attainly how *this tenant* sells.
5. **Transparent reasoning UI** — show *why* this prospect, *why* this draft, *which signals*, *deliverability risk*, *trace id*.
6. **Nurture dormant relationships** — reactivate cold contacts with cadence + rules (after core outbound loop is solid).
7. **Soft-stop vs hard-stop campaigns** — soft = no new sequences; hard = kill in-flight.
8. **Company knowledge base** — tenant knowledge blocks used in drafting + replies.
9. **Always-follows-up discipline** — scheduled follow-ups that never drop, with HITL/autopilot policy.
10. **Pipeline / outcome analytics** — deepen Attainly PnL + reply/meeting analytics (created → replied → booked → revenue), not vanity opens.

**Do NOT clone:** FirstQuadrant’s entire CRM rewrite, offline desktop app, 100M prospect DB, Perplexity-as-core (optional enrich later), unlimited-seat marketing, or anything that dilutes deliverability-first identity.

---

# ATTAINLY-NATIVE PRODUCT SYNTHESIS (what “done” looks like)

Attainly becomes:

> **Signal-stacked, deliverability-first AI revenue cockpit** that finds in-market accounts (Gojiberry DNA), then runs trustworthy human-approved execution, reply handling, and ROI proof (FirstQuadrant DNA) — without spam autonomy.

### Capability pillars (implement in this order)

| Priority | Pillar | Source DNA | Attainly reality today | Your job |
|---|---|---|---|---|
| P0 | **E2E Signal Stack ingestion → prospects** | Gojiberry | Engine + gate exist; **not production-wired E2E** | Wire a real, tested path (even if seed/fixture/provider-adapter) so a campaign with `min_signal_stack≥2` creates scored prospects with evidence |
| P0 | **Evidence-grounded drafts + Deliverability Guardian in UI** | Both | Guardian + evidence fields exist | Surface in Outbox/Campaign UI; block/risky drafts must force HITL |
| P0 | **Next Best Actions queue (Actions UX)** | FirstQuadrant | Outbox/Inbox/Operations exist | Unify operator mental model: Pending Approvals = Actions List; add snooze/reject/rerun/reason |
| P0 | **Transparent reasoning panel** | FirstQuadrant | Trace IDs exist | Show signal stack, score, cure, deliverability risk, model/trace on prospect + draft |
| P1 | **Inbound reply Brain** | FirstQuadrant | Classifier exists | Expand classifications → next-action drafts (reschedule, nurture, unsubscribe, positive→meeting) with HITL |
| P1 | **Tenant fine-tuning / knowledge** | FirstQuadrant | Partial client_cure | Add scoped natural-language rules + knowledge blocks used by personalizer/classifier |
| P1 | **Scoped Autopilot** | Both | HITL + trust-ramp after 50 | Make Autopilot explicit, scoped, default-off, and safer than silent auto-send |
| P2 | **Campaign soft/hard stop + nurture** | FirstQuadrant | Campaigns exist | Soft/hard stop; dormant reactivation flow gated by signal/rules |
| P2 | **Learning loop / weekly insights** | Gojiberry | Analytics partial | Signal-type → reply/meeting attribution; recommendations for founders |
| P3 | **Lookalikes + richer enrichment** | Gojiberry | Deferred | Only after P0–P1 proven |
| P3 | **Live CRM MCP** | Both | Contract-only | Finish only with real dependency + honest UI; else keep Prototype label |
| Later | LinkedIn multichannel | Gojiberry | Email-first | Explicitly out of scope unless founder greenlights a separate milestone |

---

# EXECUTION RULES

1. **Orient before coding.** Read `CLAUDE.md`, `docs/CLAUDE_HANDOFF_ATTAINLY.md`, relevant engine/cockpit/dashboard files. Run `git status`. Never overwrite dirty user work.
2. **Smallest high-leverage change.** Prefer wiring + surfacing what already exists over greenfield rewrites.
3. **Truth labels.** Anything incomplete must be labeled in UI/API/docs as Prototype / Mock / Blocked — never fake “CRM synced” or “LinkedIn agent live.”
4. **Tests are contracts.** Add/update tests for new behavior. Run focused tests, then broader suite when practical. Do not edit tests to force green.
5. **Tenant everywhere.** Every query/task/prospect/action/cost entry scoped by `tenant_id`.
6. **HITL for risky external actions.** Autopilot is opt-in and scoped. Deliverability `block` always forces approval.
7. **No LinkedIn automation in this mission** unless you finish P0–P1 and founder asks.
8. **No mass renames** of AutoReach / Attainly / Attainlly naming layers.
9. **Definition of done for each PR-sized chunk:** code + tests + UI states (loading/empty/error) + docs note if behavior changed + honest remaining risk.
10. **After each chunk, run Founder Validation Phase** from `CLAUDE.md` §9 and report with production-truth labels.

---

# PHASED WORK PLAN — START NOW

## Phase 0 — Make the wedge real (do this first, sequentially)

### 0.1 Audit & plan (no code yet, or minimal)
- Map exact current state of: `engine/intent/*`, `signal_stack.py`, website intake, Outbox approval, Deliverability Guardian, reply classifier, CRM MCP.
- Produce a short truth table: Real / Partial / Contract-only / Fake.
- Propose the **minimum E2E wiring** for Signal Stack that can run in demo + tests without requiring unpaid external data APIs (adapter interface + fixture/provider stub + one real provider hook if keys exist).

### 0.2 Wire Signal Stack E2E (highest leverage)
- Campaign `signal_matrix` + `min_signal_stack` must actually gate prospect creation.
- Prospects must carry `research.signal_stack.evidence` + score.
- Personalizer must refuse/vague-fallback when evidence missing (fail closed for “stacked” campaigns).
- Dashboard: show stack evidence on Contact/Prospect/Outbox draft.

### 0.3 Actions List UX (FirstQuadrant Actions → Attainly Outbox)
- Treat pending jobs as Actions: Approve / Reject / Snooze / Edit / Rerun AI.
- Show reason + deliverability risk + signal evidence inline.
- Keep one system of record (jobs/outbox) — do not fork a parallel Actions table unless necessary.

### 0.4 Transparent Reasoning Panel
- On draft/prospect: client cure, allowed signals, stack evidence, score, guardian score/fixes, trace id, HITL reason.

**Exit criteria Phase 0:** A demo user can paste website → create campaign with stacked signals → see scored prospects with evidence → see grounded draft + risk → approve → (dry-run or real) send path works → tests cover gate + evidence + HITL force-on-block.

## Phase 1 — Execution intelligence

### 1.1 Reply Brain
- Expand reply classifications into next actions with drafts + reasoning.
- Meeting cancel / OOO / positive / unsubscribe / postpone paths.

### 1.2 Fine-tuning + Knowledge
- Tenant-scoped natural-language rules (start with General + Knowledge).
- Inject into personalizer/classifier prompts with audit of which rules fired.

### 1.3 Scoped Autopilot
- Explicit toggles: Campaign Autopilot, Rule Autopilot.
- Default off. Multi-rule: all must allow.
- Replace/clarify the silent “50 sends then auto” behavior with an honest, configurable trust policy surfaced in UI.

## Phase 2 — Retention of pipeline

- Soft-stop / hard-stop campaigns.
- Nurture dormant contacts (cadence + rules + HITL).
- Weekly insights: which signal types booked meetings; what to change.

## Phase 3 — Only if Phase 0–1 are solid

- Lookalike expansion.
- Enrichment waterfall adapter (pluggable).
- Real MCP CRM sync **or** honest removal/hiding of fake CRM claims.
- (Optional separate milestone) LinkedIn channel with safety limits.

---

# IMPLEMENTATION CONSTRAINTS (technical)

- Stack: FastAPI cockpit + React dashboard + `engine/` runtime + Celery + Postgres/SQLite + Redis.
- Prefer extending: `engine/intent/`, `engine/agents/outbound_agent.py`, `engine/services/deliverability_guardian.py`, `engine/llm/*`, `cockpit/api/outbox.py`, `dashboard/src/pages/*`.
- Money = integer cents / Decimal; no unsafe float math in ledger.
- Idempotent workers; deterministic IDs where retries happen.
- Keep deliverability guardian block → forced HITL.
- ESP-aware smart dispatch + mailbox health fail-safe must not regress.
- Frontend: calm revenue cockpit (see existing `dashboard/src/styles/index.css`). No purple SaaS slop, no emoji decoration, no fake dashboards.

---

# WHAT SUCCESS LOOKS LIKE (founder demo script you must enable)

1. Signup / login
2. Paste website → auto-fill ICP / cure / signal matrix
3. Set `min_signal_stack = 2`
4. Ingest/simulate two fresh signals on an account → prospect appears with evidence
5. AI draft references those signals; guardian shows risk/fixes
6. Operator approves from Actions/Outbox
7. Send via healthy mailbox (or dry-run with honest label)
8. Reply comes in → classified → next action drafted
9. Meeting booked → PnL shows cost vs outcome
10. Trace id visible for the AI decisions

If you cannot do all 10 yet, **do 1–7 solidly first**.

---

# OUTPUT FORMAT EVERY TIME YOU FINISH A CHUNK

1. **Verdict:** Real / Prototype / Still fake — for each touched capability
2. **What changed** (files + why)
3. **Tests run + results**
4. **Demo path impact** (which step of the script improved)
5. **Risks remaining**
6. **Single next highest-leverage move**

Start with **Phase 0.1 audit**, then immediately execute **Phase 0.2** unless the audit proves Signal Stack E2E is already live (verify in code/tests, don’t trust docs).

Begin now.
