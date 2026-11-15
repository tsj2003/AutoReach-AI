# Customer-core launch self-check

**Branch:** `feature/customer-core`  
**Backup:** `backup/full-product-surface`  
**Date:** 2026-11-15  

## Verdict

**Not launch-ready for paying customers.**  
**Almost ready for a controlled pilot** after (1) this branch is deployed to Azure and (2) one live Gmail send→reply proof on production.

## What this branch fixed for pilot honesty

| Item | Status |
|------|--------|
| Nav trimmed to Dashboard / Campaigns / Mailboxes / Operations / Billing | ✅ in branch |
| Integrations / Playbooks / Signals deferred with honest page | ✅ |
| Fake dashboard “compounding loop” demo metrics removed | ✅ |
| Dashboard next-action strip (mailbox → campaign → ops) | ✅ |
| Billing: over-limit notice; no raw env-var instructions to end users | ✅ |
| Campaigns: block “New campaign” at plan cap | ✅ |
| Campaign detail: **Cancel campaign** frees a free-plan slot | ✅ |
| Landing CRM/MCP soft-down | ✅ partial |

## What production still shows (as of check)

Your Billing screenshot still shows the **old full nav** (Signals / Integrations / Playbooks). That means **Azure is not running `feature/customer-core` yet**. Local/branch work is ahead of the live app.

`/healthz` on Azure returned `ok: true` with `dry_run: false` (real-send mode). Deep `/readyz` timed out from this environment — re-check in browser before inviting anyone.

## P0 blockers before inviting a real customer

1. **Deploy** `feature/customer-core` to Azure (push + workflow_dispatch `Azure Container Apps Deploy`).  
2. **Gmail connect + one real approved send + reply** on a mailbox you control.  
3. Free-plan account at **2/1 campaigns**: cancel one unused campaign (new button) so create works again — or raise plan manually.  
4. Razorpay empty = **OK for design-partner pilots** if you upgrade tenants by hand; self-serve pay is not launch-ready.  
5. Don’t promise Firecrawl scrape / CRM / MCP until configured.

## Classification

| Surface | Grade |
|---------|--------|
| Signup / login / JWT tenancy | ✅ Production Ready (code + prior tests) |
| Campaigns + contacts | ✅ Production Ready (with plan gate) |
| Mailboxes Gmail OAuth | ⚠ Needs live proof |
| HITL approve → send | ⚠ Needs live proof (`dry_run: false` helps) |
| Inbox / replies | 🟡 Prototype→partial; unproven live |
| Billing / Razorpay | 🟡 Plan limits real; payments off |
| Integrations/MCP UI | 🔴 Deferred on this branch (correct) |

## Next highest-leverage move

Deploy this branch → connect Gmail → send one approved email to yourself → confirm reply in Inbox → then invite 1–2 design partners.
