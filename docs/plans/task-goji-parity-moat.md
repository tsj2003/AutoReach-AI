# Gojiberry Parity + Moat Loop Tracker

**PRD:** `.ralph/prd-goji-parity-moat.json`
**Branch:** `feat/signal-stack-e2e` (ahead; absorbing GP work here — one clean branch)

| ID | Title | Type | Status | Notes |
|---|---|---|---|---|
| GP-001 | Website → Agent Config | Goji | done | website_intake (Firecrawl-first + SSRF + fallback) + Campaigns auto-fill editable review; test_website_intake |
| GP-002 | Intent signal catalog + matrix UI | Goji | pending | have free-text allowed_signal_types + fail-closed; needs catalog + multiselect |
| GP-003 | ICP pre-filter | Goji | pending | net-new |
| GP-004 | Hybrid lead scoring | Goji | partial | signal-stack score (depth+recency) + Contacts column; ICP-fit component missing |
| GP-005 | Lookalikes | Goji | pending | net-new; gate through moat |
| GP-006 | Signal-grounded AI copy | Goji+Moat | partial | personalizer gets evidence + UI shows it; fail-closed completes with GP-016 |
| GP-007 | Agent email cadence | Goji | partial | OutboundAgentV1 multi-step sequences exist; needs per-campaign cadence defaults |
| GP-008 | Unified Inbox | Goji | pending | Inbox page exists — verify + next-action |
| GP-009 | Copilot / Autopilot | Goji+Moat | pending | net-new; Guardian block always HITL |
| GP-010 | Reply Brain drafts | Goji | pending | classifier exists; needs action creation |
| GP-011 | Weekly learning report | Goji | pending | net-new |
| GP-012 | Enrichment waterfall | Goji | pending | interface + mock |
| GP-013 | CRM / API / MCP | Goji | pending | MCP contract-only — keep Prototype |
| GP-014 | LinkedIn/Social safe channel | Goji | pending | drafts + caps + HITL; no cold IG/WA/FB |
| GP-015 | Deliverability Guardian | Moat | done | guardian on plan path; block→HITL; issues/fixes in Actions UI; test_guardian_gating |
| GP-016 | Evidence-gated dispatch | Moat | pending | stack gates prospect creation; SEND-time evidence gate to add |
| GP-017 | Reputation OS | Moat | pending | mailbox_health + bounce_detector exist; snapshot API + UI to add |
| GP-018 | Proof pack | Moat | partial | proof/PnL exists; add deliverability health + traces |
| GP-019 | Actions List + reasoning | Moat | done | approve/reject/snooze/edit/rerun + reasoning panel; test_actions_api, test_reasoning_api + build |
| GP-020 | Docs + demo script | Meta | pending | docs/ATTAINLY_VS_GOJIBERRY.md |

## Loop log
| Story | Result |
|---|---|
| GP-001, GP-015, GP-019 | Verified against existing tests (18 passed) → done. Absorbed from signal-stack/Actions/reasoning work already on branch. |
