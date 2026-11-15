# Moat Loop Task Tracker

**Branch:** `feat/signal-stack-e2e`  
**PRD:** `.ralph/prd-moat-loop.json`  
**Prompt:** `docs/CLAUDE_PROMPT_LOOP_ENGINEERING_MOAT.md`

| ID | Title | Status | Notes |
|---|---|---|---|
| US-001 | Actions List API controls | done | approve/reject/snooze/rerun on campaign jobs; tenant-scoped; 6 tests |
| US-002 | Actions List UI | done | Actions list on CampaignDetail: 5 verbs (Approve/Reject/Snooze/Rerun/Edit) + rows + empty state + inline editor; edit-job endpoint; build passes |
| US-003 | Reasoning panel API fields | done | job+prospect payloads carry signal_stack, guardian risk, trace id, hitl_reason; 3 tests |
| US-004 | Reasoning panel UI | done | expandable Why panel (evidence + guardian issues/fixes + trace + hitl reason) on Actions; signals column on Contacts; build passes |
| US-005 | min_signal_stack + simulate UI | pending | |
| US-006 | LLM/template honest banner | pending | |
| US-007 | Hard evidence gate (MOAT) | pending | |
| US-008 | Reputation snapshot service (MOAT) | pending | |
| US-009 | Reputation dashboard UI (MOAT) | pending | |
| US-010 | Agency proof + deliverability (MOAT) | pending | |
| US-011 | Reply Brain next actions | pending | |
| US-012 | Tenant knowledge block | pending | |
| US-013 | Scoped Autopilot | pending | |
| US-014 | Soft/hard stop | pending | |
| US-015 | Docs truth table | pending | |

**Status values:** `pending` → `in_progress` → `done` | `blocked`

## Loop log

| Time | Story | Result |
|---|---|---|
| — | — | Loop not started |
