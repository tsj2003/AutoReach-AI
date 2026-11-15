# Attainly — Customer launch readiness checklist

**Audience:** Founder preparing first real customers (controlled pilots, not mass public launch).  
**Date baseline:** 2026-11 (update as gates flip).  
**Live app:** `https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io/app/`

---

## How far are we? (honest snapshot)

| Area | Status | Meaning for customers |
|------|--------|------------------------|
| Azure app online | ✅ Mostly | `/healthz` ok; real-send mode on |
| Secrets (Gemini, Google OAuth, Cal.com) | ✅ Done earlier | App can be “configured” |
| Workers / deep readiness | 🟡 Was flaky | Confirm `/readyz?deep=true` ok before inviting |
| Signup / multi-tenant | ✅ | Customers can create accounts |
| Campaign + contacts (manual/CSV) | ✅ | Core workflow works |
| Website → ICP auto-fill | ✅ | Setup help, not buyer discovery |
| Scrape leads (Firecrawl) | ❌ Not configured | Don’t promise URL→buyers |
| Gmail connect + live send | 🟡 Code ready; **your proof incomplete** | Must prove before customers send |
| Reply detect / reply send | 🟡 Unproven live | Must prove before promising inbox AI |
| CRM / HubSpot / Slack / MCP UI | ❌ Prototype / overclaim | Do **not** sell as live |
| Marketing copy | 🟡 Partially cleaned | Still risk of overclaim on some pages |
| Paying billing / support | 🟡 Partial | Razorpay optional; support process needed |
| Paying customers / outcomes | ❌ None yet | Pilot = design partners first |

**Verdict today:** Ready for **controlled pilot customers** only after you finish the P0 list below — **not** a wide public launch.

---

## A. Must be ready before first customer (P0)

### Infrastructure
- [ ] `/healthz` → `ok: true`
- [ ] `/readyz?deep=true` → `ok: true`, `missing_required: []`
- [ ] `attainly-web`, `attainly-worker`, `attainly-beat` all Running
- [ ] Postgres + Redis healthy; backups / retention decided (even simple Azure backup)

### Account & access
- [ ] Customer can **signup** and log in (or you provision tenant)
- [ ] Password reset **or** clear “we create your login” process (no forgot-password today)
- [ ] You have an **admin/founder** account that works (don’t rely on lost smoke password)

### Outbound loop (prove once on a mailbox you control)
- [ ] Connect Gmail on production (active mailbox)
- [ ] Create campaign
- [ ] Add contactable contact (manual is fine)
- [ ] Approve → **real send** → Gmail Sent + recipient inbox
- [ ] Recipient **replies** → appears in Inbox → classify works
- [ ] Pause campaign / mailbox works (kill switch)

### Trust & legal
- [ ] Terms of use + privacy policy linked in app/signup
- [ ] Clear statement: customer owns mailbox; they approve sends
- [ ] Unsubscribe / suppression behavior explained
- [ ] No fake “Connected” CRM promises in the pilot pitch

### Support
- [ ] Single WhatsApp/email/Slack for pilot support
- [ ] 24–48h response expectation written down
- [ ] Runbook: if send fails / OAuth expires / worker down → what you do

### Pilot packaging
- [ ] Written pilot scope (1–2 pages): what’s included / excluded
- [ ] Success metric (e.g. X approved sends, Y replies, Z meetings) — honest
- [ ] Price or “design partner free / discounted” terms

---

## B. Should be ready for a smooth pilot (P1)

- [ ] Firecrawl key **only if** you promise scrape-from-URL
- [ ] Hunter key **only if** you promise enrichment
- [ ] Cal.com webhook wired if you promise booking sync
- [ ] Landing / Integrations copy stripped of HubSpot “Connected”, 15+ providers, autonomous claims
- [ ] Onboarding checklist in-app (mailbox → campaign → contact → approve)
- [ ] Sample demo tenant with fake-but-honest empty states (not fake ROI)
- [ ] Monitoring: who gets alerted if `/readyz` fails
- [ ] Data export / delete request process (GDPR-ish basic)

---

## C. Not required for first pilots (P2 — later)

- Native HubSpot / Salesforce / Slack / Clay sync
- Hosted MCP “29 tools” as a customer product
- Autonomous learning / auto-send everything
- Outlook parity
- Chrome extension as a must-have
- Scale claims (100k leads, etc.)

---

## D. Improvements to do (prioritized)

### Fix before / during first pilots
1. **Complete live Gmail proof** on production (send + reply) with your own mailbox.  
2. **Password recovery** for customers (or white-glove account creation).  
3. **Integrations page honesty** — remove fake Connected / Test & Sync success theater.  
4. **Marketing pass** — landing + inbox demo copy must match capability matrix.  
5. **Deep readyz stability** — workers must stay green; document restart procedure.  
6. **Pilot SOP** — 30-min onboarding call checklist (connect Gmail, first campaign, first approve).

### Improve product quality (next 2–4 weeks)
7. Empty states that say the **next action** (no mailbox → Connect; no contacts → Add).  
8. Clear error messages when Firecrawl/Hunter missing (not silent empty scrape).  
9. Daily/weekly email digest optional (replies waiting approval).  
10. Simple usage limits UI (“X sends left on plan”).  
11. Backup + restore drill for Postgres once.  
12. Basic status page or shared “system ok” note for pilots.

### Strategic (after 3–5 pilots with outcomes)
13. Real CRM sync (one provider done well > six fake cards).  
14. Enrichment that works end-to-end with cost shown.  
15. Proof PDF: cost vs meetings for each pilot (sales asset).

---

## E. What you can tell a customer today (honest)

**Can say**
- Multi-tenant outbound cockpit with human approval  
- Campaign + contacts + Gmail send path (once you’ve proven it)  
- Signal matrix / pause controls / cost tracking  
- We’re onboarding a small number of design partners  

**Must not say**
- Autopilot that books demos 24/7  
- Native HubSpot already connected / bi-directional CRM  
- Paste website → finds all buyers  
- 15+ enrichment providers / MCP platform ready  
- Proven ROI at scale / many customers  

---

## F. Suggested sequence (next 14 days)

| Day | Action |
|-----|--------|
| 1–2 | Signup new founder account; Connect Gmail; send+reply proof |
| 3 | Fix Integrations/landing overclaims; write 1-page pilot scope |
| 4–5 | Run full manual UI path as if you were the customer |
| 6–7 | Invite **1** friendly design partner (not 10) |
| 8–14 | Support them; capture bugs; only then invite #2–#3 |

---

## G. Go / No-Go for “customer can use it”

| Decision | When |
|----------|------|
| **NO invites** | Gmail send/reply unproven OR deep readyz red OR you still pitch fake CRM |
| **YES — 1 design partner** | P0 checklist done + you sat through one full loop yourself |
| **YES — 3–5 pilots** | First partner completed a week without P0 fires |
| **Public launch** | Multiple pilots with real replies/meetings + truthful marketing |

---

*Update this file when a checkbox moves. Linked docs: `HLD_ATTAINLY.md`, `CAPABILITY_MATRIX.md`, `ARCHITECTURE_PICTORIAL.md`.*
