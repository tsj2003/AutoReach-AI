# Branch strategy: customer-core vs full backup

| Branch | Purpose |
|--------|---------|
| `backup/full-product-surface` | **Backup.** Full Gojiberry-parity UI (Integrations/MCP, Playbooks, Signals/Visitors, Chrome extension, etc.) |
| `feature/customer-core` | **Active pilot focus.** Useful customer path only |

## On `feature/customer-core` the product focuses on

- Dashboard  
- Campaigns (+ website auto-fill, contacts, scrape UI if Firecrawl set)  
- Mailboxes (Gmail connect)  
- LinkedIn Voyager seats (Chrome extension or cookie paste) — visit / like / comment / invite / DM when seat connected; else skip to email  
- Campaign inbox / approvals  
- Operations (readiness / checklist)  
- Billing  

## Deferred (still in git on backup branch)

- Integrations & MCP page (fake Connected theater)  
- AI Playbooks free tools  
- “21 Signals & Visitors” primary nav  
- Analytics extras page  

Routes still exist but show an honest **Coming soon / deferred** page so old links don’t 404.

## How to switch

```bash
# Work on pilot product
git checkout feature/customer-core

# Recover full surface
git checkout backup/full-product-surface
```

Deploy Azure from `feature/customer-core` only after you rebuild the dashboard and verify locally.
