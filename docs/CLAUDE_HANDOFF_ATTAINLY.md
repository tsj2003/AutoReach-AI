# Attainly Claude Handoff

This document is a full-context handoff for continuing Attainly development in
Claude or another coding assistant. It is intentionally direct, practical, and
truthful. Do not treat old brainstorms as production truth without checking the
code and tests.

## 1. Identity

Current product name: **Attainly**

Repo name / older product name: **AutoReach / AutoReach AI**

GitHub repository:

```text
https://github.com/tsj2003/AutoReach-AI
```

Live demo:

```text
https://autoreach-ai-j2rdy.ondigitalocean.app/app/
```

Health endpoint:

```text
https://autoreach-ai-j2rdy.ondigitalocean.app/healthz
```

Verified on 2026-07-15:

- `/app/` returns HTTP 200.
- `/healthz` returns `{"ok": true, "version": "phase3", ...}`.

## 2. One-Line Product Definition

Attainly is a live AI revenue operations SaaS for small B2B teams. It helps
founders and agencies run safer outbound workflows with tenant-scoped campaigns,
AI-assisted drafting, human approval, deliverability-aware sending, CRM sync,
and ROI/cost reporting.

Do not describe it as a healthcare product. It is not Clinic Ops.

## 3. Honest Current Status

What is real:

- A working FastAPI + React SaaS app exists.
- It is deployed on DigitalOcean App Platform.
- It has authentication, dashboard, campaigns, contacts, inbox, operations, and billing screens.
- It has tenant-aware backend APIs.
- It has Celery worker/beat wiring for production background jobs.
- It has DigitalOcean managed Postgres and Valkey/Redis wiring.
- It has a demo login path and seeded demo-style campaign data.
- It has production readiness checks and smoke test tooling.
- It has a grant roadmap document at `docs/ATTAINLY_GRANT_ROADMAP.md`.

What is not yet proven:

- No confirmed paying customers.
- No verified real-world deliverability at scale.
- No public proof of booked meetings for real customers.
- No production Google OAuth/mailbox setup fully confirmed for a real domain.
- No custom domain/DNS setup confirmed.
- No Phoenix/observability service confirmed as live.
- No real grant approval or incorporation status confirmed.

Resume truth:

- Safe: "Built and deployed a live full-stack AI revenue operations SaaS."
- Unsafe: "Founded a funded AI startup", "enterprise-grade production platform", "serving customers", or "generating revenue" unless separately proven.

## 4. Strategic Positioning

Attainly should be positioned as:

```text
AI revenue operations cockpit for small B2B teams, agencies, and service businesses.
```

Best grant/pitch framing:

- AI productivity for Indian SMEs.
- Safe AI automation with human approval.
- Digital sales productivity.
- Auditable revenue workflows.
- Cost-efficient customer acquisition for small businesses.

Avoid:

- Healthcare-only positioning.
- Generic "AI agent" positioning.
- "Cold email spam tool" positioning.
- Billion-dollar claims without traction.

## 5. Core User Workflow

High-level product flow:

1. User signs up or logs in.
2. User creates a campaign/engagement.
3. User uploads or creates prospects/contacts.
4. Engine drafts outbound work.
5. Risky sends can land in outbox as pending approval.
6. Human approves/rejects.
7. Dispatch layer chooses safe mailbox/inbox routing.
8. Replies are detected/classified.
9. Meetings/outcomes are tracked.
10. Ledger reports COGS, revenue, and margin.
11. CRM sync can push outcomes through MCP-style worker abstraction.

## 6. Architecture Overview

Main stack:

- Python
- FastAPI
- SQLAlchemy Core
- PostgreSQL in production
- SQLite local fallback
- Celery
- Redis/Valkey
- React 19
- Vite
- Playwright/Cypress support
- DigitalOcean App Platform
- Docker
- OpenTelemetry / Phoenix wiring
- DuckDB / dlt / aiokafka for intent pipeline tests and modules

Main directories:

```text
cockpit/       FastAPI app, REST APIs, legacy operator routes, services
dashboard/     React SPA served under /app/
engine/        Agent/runtime/business logic
tests/         Pytest suite
docs/          Product, deployment, launch, grant, and platform docs
.do/           DigitalOcean App Platform spec
scripts/       Local run, smoke, launch, seed, and ops scripts
legacy/        Old/reference implementation; do not treat as active product
```

Key entrypoints:

```text
asgi.py                         Production ASGI entrypoint
cockpit/app.py                  FastAPI app factory
cockpit/main.py                 Test/import app entrypoint
celery_worker.py                Celery worker import entrypoint
engine/worker/celery_app.py     Celery config, queues, beat schedule
Dockerfile                      DigitalOcean container build
.do/app.yaml                    DigitalOcean app spec
```

## 7. Backend API Areas

Important Cockpit API modules:

```text
cockpit/api/auth.py             Signup/login/JWT/social auth config
cockpit/api/campaigns.py        Campaign CRUD and detail
cockpit/api/contacts.py         Contact/prospect APIs
cockpit/api/inbox.py            Reply inbox and orphaned reply handling
cockpit/api/meetings_api.py     Meetings APIs
cockpit/api/analytics.py        Dashboard analytics
cockpit/api/billing.py          Billing config/plans/usage
cockpit/api/dashboard.py        Campaign PnL endpoint
cockpit/api/mailboxes.py        Tenant mailbox connect/status
cockpit/api/outbox.py           HITL outbox pending/approve/reject
cockpit/api/operations.py       Readiness, mission control, onboarding
```

Important Cockpit services:

```text
cockpit/services/readiness.py          Production readiness checks
cockpit/services/launch_checklist.py   Campaign launch safety checks
cockpit/services/onboarding.py         Pilot onboarding flow
cockpit/services/preflight.py          SPF/DMARC/domain checks
```

## 8. Engine Areas

Important engine modules:

```text
engine/runtime/context.py       TenantContext, ExecutionResult, WorkerExecutionContext
engine/runtime/runtime.py       AgentEngineRuntime and dispatch flow
engine/runtime/mcp_worker.py    MCP worker context
engine/integrations/mcp_gateway.py
engine/telemetry/provider.py    OpenTelemetry provider setup
engine/telemetry/tracer.py      TracedWorkerContext
engine/services/mailbox_health.py
engine/dispatch/router.py       SmartInboxRouter
engine/dispatch/provider.py     SMTPProvider abstraction
engine/dispatch/adapter.py      Smart routed email adapter
engine/intent/models.py         IntentSignal, IntentIngestionResult
engine/intent/publisher.py      Redpanda/Kafka publisher
engine/intent/repository.py     DuckDB intent repository
engine/intent/ingestor.py       Intent signal -> prospect bridge
engine/billing/ledger.py        CostEntry, PnLReport, LedgerService
engine/workflows/crm_sync.py    CRM sync through MCP worker
engine/evals/loop.py            Agent eval loop
engine/tasks.py                 Celery dispatch/HITL-related tasks
```

Key queues:

```text
engine
maintenance
standard-agents
```

The worker command in production consumes all three:

```text
celery -A celery_worker.celery_app worker --loglevel=info --concurrency=2 -Q engine,maintenance,standard-agents
```

Celery beat schedules:

- `engine.tick_all_active` every 60s.
- `engine.reset_daily_caps` daily.
- `engine.warmup_tick_all` daily.

## 9. Frontend Areas

React app lives in:

```text
dashboard/src/
```

Important files:

```text
dashboard/src/App.jsx
dashboard/src/api/client.js
dashboard/src/contexts/AuthContext.jsx
dashboard/src/components/Layout.jsx
dashboard/src/pages/Login.jsx
dashboard/src/pages/Signup.jsx
dashboard/src/pages/Dashboard.jsx
dashboard/src/pages/Campaigns.jsx
dashboard/src/pages/CampaignDetail.jsx
dashboard/src/pages/Contacts.jsx
dashboard/src/pages/Inbox.jsx
dashboard/src/pages/Operations.jsx
dashboard/src/pages/OperationsOnboarding.jsx
dashboard/src/pages/Billing.jsx
dashboard/src/styles/index.css
```

Production serving:

- Vite builds the React app into `cockpit/static/dashboard`.
- FastAPI serves it at `/app/`.
- Deep links like `/app/login` fall back to the SPA.

## 10. Deployment

Current deployment provider:

```text
DigitalOcean App Platform
```

Spec:

```text
.do/app.yaml
```

Components:

- `autoreach-web` web service.
- `autoreach-worker` Celery worker.
- `autoreach-beat` Celery beat.
- Managed Postgres.
- Managed Valkey/Redis.

Important deployment fix already made:

- DigitalOcean Valkey gives a `rediss://` URL.
- Celery requires `ssl_cert_reqs`.
- `engine/worker/celery_app.py` normalizes `rediss://` URLs by adding `ssl_cert_reqs=CERT_REQUIRED` if missing.

Do not create another DigitalOcean app unless intentionally replacing this one.
The existing app ID is managed externally through DigitalOcean; avoid duplicating
billable resources.

## 11. Environment Variables

See `.env.example`, `README.md`, and `docs/DEPLOYMENT.md`.

Critical production vars:

```text
DATABASE_URL
REDIS_URL
AUTOREACH_JWT_SECRET
AUTOREACH_SESSION_SECRET
AUTOREACH_CREDENTIAL_ENCRYPTION_KEY
AUTOREACH_ENABLE_CONSOLE=0
AUTOREACH_RUNTIME_SMART_DISPATCH=1
AUTOREACH_WORKER_QUEUES=engine,maintenance,standard-agents
AUTOREACH_PUBLIC_BASE_URL=https://autoreach-ai-j2rdy.ondigitalocean.app
CALCOM_WEBHOOK_SECRET
GEMINI_API_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_SIGNIN_CLIENT_ID
AUTOREACH_PHOENIX_ENDPOINT
AUTOREACH_INTENT_DUCKDB_PATH
```

Security warning:

- Do not print or commit real secrets.
- `credentials.json` exists in the repo tree. Before public/commercial use,
  inspect it, remove if sensitive, and rotate any exposed Google credentials.
- Do not include DigitalOcean database URLs, Redis URLs, JWT secrets, OAuth secrets,
  or generated tokens in docs or chat responses.

## 12. Local Development

Typical local setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_cockpit.py
```

React dashboard:

```bash
npm ci --prefix dashboard
npm run build --prefix dashboard
```

Local cockpit default:

- SQLite if `DATABASE_URL` is not set.
- Console email adapter if Gmail credentials are not set.

## 13. Testing

Main backend tests:

```bash
python3 -m pytest tests
```

Focused production tests:

```bash
python3 -m pytest tests/test_production_wiring.py tests/test_production_readiness.py -q
python3 -m pytest tests/test_digitalocean_deployment.py -q
```

Production smoke:

```bash
python3 scripts/production_smoke.py \
  --base-url https://autoreach-ai-j2rdy.ondigitalocean.app \
  --email smoke-do@autoreach.ai \
  --password 'Password1!' \
  --company 'AutoReach Smoke' \
  --timeout 30
```

Known caveat:

- Some old/legacy test paths may require optional Playwright/browser dependencies.
- Prefer `python3 -m pytest tests` for the active project suite.
- If CI fails, inspect the exact GitHub Actions log before changing code.

## 14. Important Product Rules

Tenant isolation:

- Every runtime task must carry `tenant_id`.
- Never reintroduce a global unscoped `plan_all()` loop that can act across tenants unsafely.
- Campaign/outbox/dashboard endpoints must filter by tenant.

HITL:

- Risky outbound actions should be reviewable.
- Approval moves outbox jobs to `APPROVED`.
- Rejection moves jobs to `REJECTED`.
- Approved sends should route to the safe dispatch queue.

Deliverability:

- Do not round-robin blindly through mailboxes.
- Use mailbox health keyed by `mailbox_id`.
- Burned/paused mailboxes must be skipped.

Intent:

- Missing or empty signal matrix should fail closed.
- Allowed signal types come from campaign metadata.
- Account-level prospects without email are allowed, but should not be sendable until enriched.

Observability:

- New agent/workflow actions should preserve trace IDs where possible.
- Use OpenTelemetry/OpenInference-style span attributes consistently.

CRM sync:

- Do not add brittle direct Salesforce/HubSpot code unless explicitly scoped.
- Current intended path is MCP worker abstraction.

## 15. Current Dirty Worktree Notes

At the time this handoff was created:

```text
docs/ATTAINLY_GRANT_ROADMAP.md
```

was untracked or newly created locally. Check `git status --short` before making
changes. Do not overwrite user work.

## 16. Grant / Founder Context

Founder wants grants for Attainly, not Clinic Ops.

Grant roadmap:

```text
docs/ATTAINLY_GRANT_ROADMAP.md
```

Best current grant route:

- External incubators.
- Startup India listed incubators.
- State startup missions.
- Student/young founder programs.
- AI/SaaS/SME digitization framing.

Do not assume the founder's college has an incubation cell. It does not.

## 17. Resume Context

Safe resume wording:

```text
Built and deployed Attainly, a live AI revenue operations SaaS using FastAPI,
React, PostgreSQL, Celery, Redis/Valkey, Docker, and DigitalOcean.
```

Safe bullets:

- Built tenant-scoped campaign, contact, inbox, analytics, and billing workflows.
- Implemented HITL approval for AI-generated outbound jobs.
- Added deliverability-aware smart inbox routing and mailbox health checks.
- Integrated background execution with Celery worker/beat and production readiness probes.
- Built AI workflow infrastructure for reply classification, intent ingestion, CRM sync, and ROI/PnL reporting.

Unsafe unless later proven:

- Paying customers.
- Funded startup.
- Enterprise adoption.
- Proven revenue.
- Large-scale production deliverability.

## 18. Recommended Next Development Path

If Claude continues this project, work in this order:

### Step 1: Stabilize CI

Investigate GitHub Actions failures before adding features.

Actions:

- Open latest failed workflow logs.
- Reproduce locally.
- Fix dependency/version/test isolation issues.
- Keep active tests green.

### Step 2: Clean Secret Hygiene

Actions:

- Inspect `credentials.json`.
- Remove sensitive files from git if needed.
- Rotate any exposed OAuth credentials.
- Update `.gitignore`.
- Add a secret-scanning note/check if needed.

### Step 3: Improve Demo Quality

Actions:

- Ensure demo account works on live app.
- Make dashboard look coherent for screen recording.
- Add sample campaigns, contacts, inbox replies, and ROI proof.
- Make "Use demo account" reliable.

### Step 4: Real Pilot Readiness

Actions:

- Add real domain/custom domain.
- Configure Google OAuth for production URL.
- Configure Cal.com webhook.
- Configure Phoenix endpoint or disable the warning clearly.
- Add a simple pilot onboarding checklist.

### Step 5: Grant Assets

Actions:

- Create `docs/ATTAINLY_ONE_PAGE_BRIEF.md`.
- Create `docs/ATTAINLY_PITCH_DECK_OUTLINE.md`.
- Create a 2-minute demo script.
- Create a list of 20 customer interview targets.

### Step 6: Product Hardening

Actions:

- Expand test coverage around tenant isolation.
- Improve mailbox health persistence.
- Make outbox/approval UI clearer.
- Add audit trail UI for AI reasoning/trace IDs.
- Add admin-safe demo reset command.

## 19. Do Not Do

Do not:

- Rename everything blindly from AutoReach to Attainly without a planned migration.
- Delete legacy folders without checking imports/tests.
- Commit secrets.
- Reset git history or run destructive git commands.
- Claim traction that does not exist.
- Add huge new frameworks before reading local patterns.
- Build SMS/WhatsApp provider integrations before validating pilot demand.
- Build healthcare-specific flows unless the founder explicitly pivots.

## 20. First Message Claude Should Read

Suggested prompt for Claude:

```text
You are continuing development on Attainly, formerly AutoReach AI. Read
docs/CLAUDE_HANDOFF_ATTAINLY.md, README.md, docs/DEPLOYMENT.md,
docs/DIGITALOCEAN_DEPLOYMENT.md, docs/LIVE_OPS_RUNBOOK.md, and
docs/ATTAINLY_GRANT_ROADMAP.md before changing code.

Do not assume the product is Clinic Ops. It is Attainly: an AI revenue operations
SaaS for small B2B teams.

First, run git status and inspect the latest CI failure. Then propose and apply
the smallest safe fix. Do not modify tests unless the user explicitly asks.
```

## 21. Final Truth

Attainly is a serious engineering project and a live SaaS prototype. It is not
yet a validated startup. The next goal is not more architecture for its own sake;
the next goal is proof:

- stable CI,
- clean demo,
- grant/pilot materials,
- real user conversations,
- first pilot,
- then incorporation/DPIIT/grant applications.
