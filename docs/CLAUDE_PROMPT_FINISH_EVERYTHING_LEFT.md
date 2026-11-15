# Claude Prompt — Finish Everything Left (Attainly Phase 0 → Pilot-Ready)

> Paste this entire prompt into Claude Code with the **AutoReach-AI** repo open.
> Obey `CLAUDE.md` as law. Do not restart finished work. Continue from the live branch state.

---

## COPY EVERYTHING BELOW THIS LINE INTO CLAUDE

---

# ROLE

You are founder-level Claude Code inside **Attainly** (`/Users/tarandeepsinghjuneja/AutoReach-AI`).

Your job: **finish everything left** to make the founder demo and pilot path undeniable — from the current `feat/signal-stack-e2e` branch through the rest of Phase 0, then Phase 1, then Phase 2 pilot essentials.

Read and obey **`CLAUDE.md`**. If this prompt conflicts with tenant isolation, HITL, deliverability fail-safe, intent discipline, auditability, ROI ledger, secret hygiene, or production truth — **`CLAUDE.md` wins**.

**Do not** build Instagram / Facebook / WhatsApp cold automation or Meta Ads management. Stay on-wedge: deliverability-safe email + signal-stacked research + trustworthy agent execution.

---

# CURRENT STATE (TRUST THIS — DO NOT RE-DO)

Branch: **`feat/signal-stack-e2e`** (commit ~`e6d2778` or later on this branch). Stay on this branch until Phase 0 UI is done; then open one PR for Phase 0.

### Already REAL (do not rebuild)
- Campaign `min_signal_stack` in create/patch/response — tested
- `POST /api/campaigns/{id}/signals/simulate` — tenant-scoped, runs real `IntentProspectIngestor` + `SignalStackPolicy`
- `engine/intent/memory_repository.py` — feeds ingestor without Kafka/DuckDB
- Outbound agent threads signal evidence into personalizer (`research=`) + Guardian grounding terms
- Tests: `tests/test_signal_stack_e2e.py` + suite previously **414 passed**
- Founder has provided an **LLM API key** (Gemini and/or OpenAI in `.env`). Use it; do not ask them to paste secrets into chat. Never commit `.env` or keys.

### Still NOT done (your mission)
1. **Live external signal ingestion** — still Prototype (simulate-only is OK if labeled; do not fake Kafka)
2. **UI surfaces** — evidence, Guardian risk/fixes, trace id not in cockpit yet
3. **Actions List UX** — Pending Approvals not yet framed as FQ-style Actions
4. **Phase 1** — Reply Brain, fine-tuning/knowledge, scoped Autopilot
5. **Phase 2** — soft/hard stop, nurture, weekly insights
6. Merge/PR Phase 0 when UI demo path works

---

# NORTH STAR DEMO (must work end-to-end)

A founder can, in the **UI** (not only API):

1. Login
2. Create/edit campaign → set `min_signal_stack = 2`
3. Simulate/ingest **1** signal → **no** prospect (gate holds)
4. Simulate/ingest **2** distinct fresh signals → prospect appears with **stack evidence** visible
5. Outbox/Actions shows draft with:
   - cited signal evidence
   - Deliverability Guardian score + issues/fixes
   - openinference / trace id
   - Approve / Reject / Snooze / Edit / Rerun
6. With LLM key present, draft **visibly references** evidence (not bare template)
7. Approve → dispatch path works (dry-run OK if labeled)
8. (Phase 1+) Reply comes in → classified → next action drafted with reasoning
9. Meeting + cost/ROI visible

Ship **1–7 first** (rest of Phase 0). Then Phase 1. Then Phase 2.

---

# EXECUTION PLAN — FINISH IN ORDER

## PHASE 0.3 — Actions List UX (do next, immediately)

Make Pending Approvals / Outbox read as an **Actions List** (FirstQuadrant DNA) without forking a second system of record.

**Requirements**
- Single system of record = existing jobs/outbox
- Each action row shows: contact/company, campaign, action type, short reason, status
- Controls: **Approve / Reject / Snooze / Edit / Rerun AI** (implement what exists; add Snooze/Rerun if missing with tests)
- Block-level Guardian risk must force / keep HITL (do not regress)
- Empty / loading / error states
- Tenant-scoped APIs only

**Exit criteria:** Operator can clear a queue of pending drafts from one screen with clear verbs.

## PHASE 0.4 — Transparent Reasoning Panel (same PR as 0.3 if possible)

On Prospect view + Outbox/Action detail:

Show:
- `client_cure` (summary)
- allowed / stacked signals used
- `research.signal_stack.evidence` (citations)
- stack score
- Guardian score + issue codes + suggested fixes
- trace / openinference id
- why HITL is required (if forced)

**Exit criteria:** Demo does not need curl to prove Signal Stack or Guardian.

## PHASE 0.5 — Demo polish + LLM verification

- Verify with real key (without printing secrets): plan a draft after 2-signal simulate → body references evidence
- If Gemini quota still fails, ensure OpenAI path works where wired (critic/personalizer) OR clear fallback banner: “LLM unavailable — template draft”
- Campaign UI control for `min_signal_stack`
- Button or clear flow to simulate signals in Operations/Campaign detail for demo (dev/demo-safe; do not expose as fake “live radar” without label)
- Label simulate: **“Simulate signals (demo/ingest)”** — honest

**Exit criteria:** Recordable UI demo for steps 1–7.

## PHASE 0.6 — PR readiness

- All Phase 0 tests green
- Update docs briefly: what is Real vs Simulate-only vs still Prototype
- Do **not** claim live Kafka/provider ingestion
- Prepare PR summary for `feat/signal-stack-e2e` → main
- **Ask before merging** unless founder already said merge

---

## PHASE 1 — Execution intelligence (after Phase 0 UI done)

### 1.1 Reply Brain
- Expand reply classification → next actions: positive, OOO, postpone, unsubscribe, meeting cancel/no-show, competitor
- Draft next action + reasoning into Actions List
- HITL by default

### 1.2 Tenant fine-tuning + knowledge
- Natural-language rules: start with **General + Knowledge** (Email/Note can follow)
- Scope to campaign/tenant
- Inject into personalizer/classifier; audit which rules fired

### 1.3 Scoped Autopilot
- Explicit toggles: Campaign Autopilot, Rule Autopilot — **default off**
- Multi-rule: autopilot only if all applicable rules allow
- Replace/clarify silent “50 sends then auto” with honest, configurable trust policy **surfaced in UI**
- Guardian `block` always overrides Autopilot → HITL

**Exit criteria:** Reply → next action works in UI; Autopilot is explicit and safe.

---

## PHASE 2 — Pipeline retention (pilot essentials only)

### 2.1 Campaign soft-stop / hard-stop
- Soft: no new sequences; in-flight may finish
- Hard: stop everything immediately
- Clear UI + API + tests

### 2.2 Nurture Agent (MVP)
- Re-engage dormant contacts with cadence + instructions
- HITL/Autopilot scoped
- Do not spam; respect signal/cure constraints

### 2.3 Weekly insights (Analyst MVP)
- Which signal types → replies/meetings
- Simple recommendations (not silent self-rewriting brand voice)
- Tie into existing analytics/PnL where possible

**Exit criteria:** Pilot customer can stop campaigns safely, nurture cold leads, see what worked.

---

## EXPLICITLY OUT OF SCOPE (refuse unless founder overrides in writing)

- Cold Instagram / Facebook / WhatsApp DM automation
- Meta Ads spend platform
- Fake live intent radar without providers
- Mass rename AutoReach / Attainly / Attainlly
- CRM MCP “live” claims without real MCP dependency + test
- Burning tests to force green

**Deferred OK:** lookalikes, enrichment waterfall, LinkedIn sending, Firecrawl swap (nice-to-have during 0.5 if quick win for website intake — only if it doesn’t block Actions UI).

---

# ENGINEERING RULES

1. `git status` first — never overwrite dirty unrelated user work
2. Stay on `feat/signal-stack-e2e` until Phase 0 UI complete
3. Smallest high-leverage diffs; reuse outbox/jobs
4. Tenant scope everywhere
5. Add/update tests for every behavior change
6. Run focused tests, then broader suite when practical
7. No secrets in git, logs, or PR text
8. Calm ops cockpit UI — no decorative slop
9. After each chunk: report in the format below
10. Founder Validation Phase (`CLAUDE.md` §9) before calling anything done

---

# OUTPUT FORMAT (every chunk)

1. **Verdict** per capability: Real / Prototype / Still fake
2. **What changed** (files + why)
3. **Tests run + results**
4. **Demo path impact** (which north-star steps improved)
5. **Risks remaining**
6. **Single next highest-leverage move**

---

# START NOW

1. Confirm branch `feat/signal-stack-e2e` and that Phase 0.2 files/tests still exist.
2. Implement **Phase 0.3 Actions List** immediately.
3. Implement **Phase 0.4 Reasoning Panel** on the same branch.
4. Do **0.5** LLM/demo polish.
5. Stop and report for PR decision before Phase 1 — unless 0.3–0.5 are done and you can continue cleanly into 1.1 in the same session.

Begin with Phase 0.3 now. No re-litigation of multichannel ads. No restart of Signal Stack E2E API work.
