# AutoReach

[![CI](https://github.com/tsj2003/AutoReach-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/tsj2003/AutoReach-AI/actions/workflows/ci.yml)

**AI agent execution platform for outbound-as-a-service.**

AutoReach is an operator-run engine that books qualified B2B meetings at scale.
The first product on top is **outbound-as-a-service (OaaS)**: you give an engagement
an offer, a prospect list, and a calendar link; the engine personalizes, sends,
detects replies, classifies them with Gemini, drafts responses, and books meetings.
The second product (Phase 6) is the public platform SDK — runtime infrastructure
for any AI agent that takes real-world actions.

See `docs/PLATFORM.md` for the thesis. See `docs/DEPLOYMENT.md`,
`docs/DIGITALOCEAN_DEPLOYMENT.md`, and `docs/LIVE_OPS_RUNBOOK.md` for
production launch setup.

---

## Quick start (single-operator cockpit)

```bash
# 1. Install Python deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Copy + fill env
cp .env.example .env   # edit with your keys

# 3. Start the cockpit
python scripts/run_cockpit.py
# → opens http://127.0.0.1:8765
```

### Connect Gmail (optional — cockpit works without it)

The cockpit defaults to a console adapter (no real emails). To send real emails:

1. Go to [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID (Desktop / Web App type)
3. Add `http://127.0.0.1:8765/oauth/google/callback` as an authorized redirect URI
4. Set env vars:
   ```
   GOOGLE_CLIENT_ID=your_client_id
   GOOGLE_CLIENT_SECRET=your_client_secret
   AUTOREACH_GMAIL_SENDER=you@yourdomain.com
   ```
5. Click **Connect Gmail** in the cockpit topbar → follow the OAuth flow
6. Topbar changes from "Console adapter (dev)" to "Gmail · LIVE"

To test without sending real emails, set `AUTOREACH_GMAIL_DRY_RUN=1`.

---

## Environment variables

```bash
# ── Database ────────────────────────────────────────────────────────────────
DATABASE_URL=                               # production Postgres
AUTOREACH_DB=sqlite:///autoreach_engine.db  # local fallback when DATABASE_URL is empty

# ── Gmail ───────────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
AUTOREACH_GMAIL_SENDER=you@yourdomain.com
AUTOREACH_GMAIL_TOKEN_PATH=token.json       # default
AUTOREACH_GMAIL_DRY_RUN=0                  # set to 1 to simulate sends
AUTOREACH_OAUTH_REDIRECT_URI=http://127.0.0.1:8765/oauth/google/callback

# ── Gemini ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY=                             # enables reply classification + personalization

# ── Cal.com webhook ─────────────────────────────────────────────────────────
CALCOM_WEBHOOK_SECRET=                      # required in production; from Cal.com Settings → Webhooks

# ── Cockpit ─────────────────────────────────────────────────────────────────
AUTOREACH_SESSION_SECRET=                   # random by default (sessions reset on restart)
AUTOREACH_JWT_SECRET=                       # required in production
AUTOREACH_CREDENTIAL_ENCRYPTION_KEY=        # required in production; Fernet key for mailbox OAuth secrets
AUTOREACH_ENABLE_CONSOLE=0                  # required in production; legacy console is unauthenticated
AUTOREACH_RUNTIME_SMART_DISPATCH=0          # set to 1 in production for health-gated tenant mailbox routing

# ── Redis / workers ─────────────────────────────────────────────────────────
REDIS_URL=                                  # required in production
AUTOREACH_WORKER_QUEUES=engine,maintenance,standard-agents

# ── Reasoning ledger / intent ingestion ─────────────────────────────────────
AUTOREACH_PHOENIX_ENDPOINT=                 # e.g. http://phoenix:6006/v1/traces
AUTOREACH_INTENT_DUCKDB_PATH=               # required before scheduling intent ingestion
AUTOREACH_INTENT_HOURS_BACK=24

# ── Monitoring (optional) ────────────────────────────────────────────────────
SENTRY_DSN=
POSTHOG_API_KEY=
```

---

## Architecture

```
cockpit/          FastAPI + Jinja2 operator console (http://127.0.0.1:8765)
├── routes/       engagements, prospects, replies, meetings, oauth, webhooks
├── templates/    server-rendered HTML
└── static/       cockpit.css

engine/           Product-agnostic AI agent execution platform
├── core/         types, state machine, protocols
├── adapters/     email_gmail_real, email_console, gmail_token_store
├── agents/       OutboundAgentV1 (first-touch + personalization)
├── runtime/      EngineRuntime, AdapterRegistry, contexts
├── storage/      SQLite via SQLAlchemy Core (Postgres-ready)
├── services/     operations, PnL, CSV ingest, reply detector
└── llm/          Gemini client, reply classifier, outbound personalizer

scripts/          run_cockpit.py, live_ops_launch.py, production_smoke.py, e2e_saas_smoke.py
tests/            339 tests (pytest)
docs/             MASTER_PLAN.md, PLATFORM.md, IMPLEMENTATION_PLAN.md
legacy/           pre-pivot Flask SaaS shell (reference only, not on import path)
landing-page/     Vite + React 19 marketing site (npm run dev)
```

---

## Key capabilities (what's built today)

| Capability | Status |
|---|---|
| Engagement + prospect management | ✅ |
| CSV upload (email, name, company, title) | ✅ |
| Gmail send via OAuth (real + dry-run) | ✅ |
| HITL trust ramp (first N sends require approval) | ✅ |
| Retry / dead-letter / exponential backoff | ✅ |
| Job state machine with crash-resume | ✅ |
| Gemini reply classification (interested / objection / auto / unsubscribe) | ✅ |
| Gmail reply detection (polls per-thread, idempotent) | ✅ |
| Cockpit reply triage queue | ✅ |
| Gemini AI-drafted reply suggestions | ✅ |
| Gemini outbound personalization | ✅ |
| Per-engagement P&L (revenue − cost) | ✅ |
| Meeting booking + qualify / no-show / cancel | ✅ |
| Cal.com webhook → auto-book meeting | ✅ |
| Google OAuth flow (connect Gmail from the cockpit) | ✅ |
| Cost ledger (LLM + email send) | ✅ |
| Structured event log (append-only audit trail) | ✅ |
| Tenant isolation + Celery/MCP worker contexts | ✅ |
| Intent ingestion + prospect bridge | ✅ |
| HITL outbox API + smart inbox router | ✅ |
| Health-gated approved email dispatch via tenant mailboxes | ✅ |
| Smart runtime email dispatch feature flag for production | ✅ |
| Engagement-scoped Celery campaign ticks | ✅ |
| Tenant-mailbox Gmail reply polling | ✅ |
| Legacy direct-send safety gates + scoped console controls | ✅ |
| Legacy OAuth closure in production deploy gate | ✅ |
| Production-required Cal.com webhook signing | ✅ |
| Mailbox OAuth credential encryption at rest | ✅ |
| Live deploy smoke rejects unsigned booking webhooks | ✅ |
| Global mailbox maintenance across tenants | ✅ |
| Tenant-scoped Cal.com booking webhook matching | ✅ |
| Live deploy smoke validates signed booking webhooks | ✅ |
| Live deploy smoke can exercise scoped booking webhooks | ✅ |
| API-created prospects inherit tenant ownership | ✅ |
| Production-safe mailbox OAuth redirect validation | ✅ |
| Render worker/beat credential-secret wiring | ✅ |
| Production JWT dev-secret fail-closed guard | ✅ |
| OpenTelemetry/Phoenix reasoning ledger wiring | ✅ |
| Live ops launch planner for deploy/secrets/DNS/OAuth/Cal.com/Phoenix | ✅ |
| Internal OaaS operations console | ✅ |
| Production readiness checker + deep DB/Redis/worker probes | ✅ |

---

## Running tests

```bash
python3 -m pytest tests
# 339 passed
```

Browser E2E tests live in `dashboard/`; see `docs/BROWSER_E2E.md` for
Playwright codegen, Playwright CI-style specs, and Cypress visual runs.

---

## What's next

See `docs/LIVE_OPS_RUNBOOK.md` before onboarding a paid pilot. The Cockpit
Operations page now exposes production readiness, pilot onboarding, campaign
launch checklists, mission control, and customer proof packages.

---

## License

MIT. Built by Tarandeep Singh Juneja.
