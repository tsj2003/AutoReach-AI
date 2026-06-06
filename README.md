# AutoReach

[![CI](https://github.com/tsj2003/AutoReach-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/tsj2003/AutoReach-AI/actions/workflows/ci.yml)

**AI agent execution platform for outbound-as-a-service.**

AutoReach is an operator-run engine that books qualified B2B meetings at scale.
The first product on top is **outbound-as-a-service (OaaS)**: you give an engagement
an offer, a prospect list, and a calendar link; the engine personalizes, sends,
detects replies, classifies them with Gemini, drafts responses, and books meetings.
The second product (Phase 6) is the public platform SDK — runtime infrastructure
for any AI agent that takes real-world actions.

See `docs/PLATFORM.md` for the thesis. See `docs/MASTER_PLAN.md` for the roadmap.

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
DATABASE_URL=sqlite:///autoreach_engine.db  # default
# or: postgresql://user:pass@localhost:5432/autoreach

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
CALCOM_WEBHOOK_SECRET=                      # from Cal.com Settings → Webhooks

# ── Cockpit ─────────────────────────────────────────────────────────────────
AUTOREACH_SESSION_SECRET=                   # random by default (sessions reset on restart)

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

scripts/          run_cockpit.py, demo_phase1.sh
tests/            102 tests (pytest)
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

---

## Running tests

```bash
.venv/bin/python -m pytest tests/ -q
# 102 passed
```

---

## What's next

See `docs/MASTER_PLAN.md`. Next milestones:

- **M1** — JWT auth + multi-tenant data model
- **M2** — FastAPI REST API for the React SPA
- **M4** — Database-backed OAuth mailboxes (multi-user)
- **M3** — React SPA dashboard (replaces Jinja cockpit for end users)
- **M5** — Rate limits + tier enforcement
- **M6** — AI reply agent autopilot mode

---

## License

MIT. Built by Tarandeep Singh Juneja.
