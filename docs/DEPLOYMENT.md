# AutoReach — Deployment Guide

Production deploy to DigitalOcean, Render, or any Docker host. Supersedes the legacy
`legacy/docs/BETA_LAUNCH.md`.

---

## Architecture in production

```
                    ┌──────────────┐
   Browser ───────► │  web (ASGI)  │  gunicorn + uvicorn, serves API + React SPA
                    └──────┬───────┘
                           │
              ┌────────────┼─────────────┐
              ▼            ▼              ▼
        ┌─────────┐  ┌──────────┐  ┌───────────┐
        │ Postgres│  │  Redis   │  │  Gmail /  │
        │ (state) │  │ (broker) │  │  Gemini   │
        └─────────┘  └────┬─────┘  └───────────┘
                          │
              ┌───────────┴──────────┐
              ▼                      ▼
        ┌──────────┐          ┌──────────┐
        │  worker  │          │   beat   │
        │ (celery) │          │ (celery) │
        └──────────┘          └──────────┘
```

- **web** — FastAPI (API + serves the built React SPA at `/app/`)
- **worker** — Celery, runs `engine.tick_*` / `engine.poll_replies` tasks
- **beat** — Celery beat, schedules ticks (60s), daily cap reset, warmup ramps
- **Postgres** — all tenant/campaign/prospect/event state
- **Redis** — Celery broker + result backend

In dev (no `REDIS_URL`), there's no worker/beat — the cockpit runs ticks inline.

---

## Deploy to DigitalOcean App Platform

Use this path if you want a simple always-on deployment without free-tier cold
starts. The repo includes `.do/app.yaml` for web, worker, beat, Postgres, and
Redis.

See `docs/DIGITALOCEAN_DEPLOYMENT.md`.

Quick shape:

```bash
python3 scripts/live_ops_launch.py generate-secrets --dotenv
# edit .do/app.yaml placeholders, then:
doctl apps create --spec .do/app.yaml
```

---

## Deploy to Render (Blueprint)

1. Push the repo to GitHub.
2. Render Dashboard → **New → Blueprint** → select the repo.
3. Render reads `render.yaml` and provisions: web, worker, beat, Postgres, Redis.
4. Fill in the `sync: false` env vars in the dashboard:
   - `GEMINI_API_KEY`
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
   - `AUTOREACH_PHOENIX_ENDPOINT` for the reasoning ledger
   - `AUTOREACH_INTENT_DUCKDB_PATH` before scheduling intent ingestion
   - `CALCOM_WEBHOOK_SECRET` for verified booking webhooks
   - `SENTRY_DSN` for runtime error monitoring
5. `AUTOREACH_JWT_SECRET` and `AUTOREACH_SESSION_SECRET` are auto-generated.
6. First deploy runs DB schema creation automatically (`metadata.create_all`).

### Live ops launch planner

After the web service has a public URL, generate the operator plan:

```bash
python3 scripts/live_ops_launch.py generate-secrets

export AUTOREACH_SMOKE_PASSWORD='choose-a-strong-smoke-password'
python3 scripts/live_ops_launch.py plan \
  --base-url https://autoreach-web.onrender.com \
  --domain yourdomain.com \
  --smoke-email smoke@yourdomain.com \
  --strict
```

The planner derives the Google OAuth redirect URI, Cal.com webhook URL, DNS
preflight command, Phoenix reminder, and final production smoke command without
printing configured secret values. See `docs/LIVE_OPS_RUNBOOK.md`.

### Google OAuth redirect URI
After the web service is live at `https://autoreach-web.onrender.com`, add this
to your Google Cloud OAuth client's authorized redirect URIs:
```
https://autoreach-web.onrender.com/api/mailboxes/connect/callback
```

---

## Deploy with Docker Compose (self-host)

```bash
cp .env.example .env   # fill in secrets
docker compose up --build
```

`docker-compose.yml` runs web + worker + beat + redis + postgres.

---

## Environment variables

| Var | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | prod | Postgres connection string (auto from Render) |
| `REDIS_URL` | prod | Celery broker (auto from Render) |
| `AUTOREACH_JWT_SECRET` | **yes** | JWT signing key — set a strong random value |
| `AUTOREACH_SESSION_SECRET` | yes | OAuth session cookie key |
| `AUTOREACH_CREDENTIAL_ENCRYPTION_KEY` | **yes** | Fernet key for mailbox OAuth credentials at rest |
| `AUTOREACH_RUNTIME_SMART_DISPATCH` | **yes** | set to `1` so runtime email jobs use health-gated tenant mailbox routing |
| `AUTOREACH_PUBLIC_BASE_URL` | recommended | public app origin used to validate mailbox OAuth redirects |
| `GEMINI_API_KEY` | for AI | reply classification + personalization |
| `GOOGLE_CLIENT_ID` / `_SECRET` | for Gmail | OAuth mailbox connection |
| `AUTOREACH_PHOENIX_ENDPOINT` | recommended | OTLP endpoint for Phoenix reasoning ledger |
| `AUTOREACH_INTENT_DUCKDB_PATH` | for intent | local/persistent DuckDB path for intent ingestion |
| `AUTOREACH_WORKER_QUEUES` | yes | should include `engine,maintenance,standard-agents` |
| `CALCOM_WEBHOOK_SECRET` | **yes** | verifies public Cal.com booking webhooks |
| `SENTRY_DSN` | optional | error monitoring |

---

## Cal.com Booking Metadata

Production booking webhooks are tenant-scoped. Include `tenant_id` and either
`engagement_id` or `campaign_id` in the Cal.com booking metadata/custom fields
for each campaign. Unscoped production webhooks are acknowledged but do not
create meetings, preventing email-only matching from crossing tenant boundaries.

---

## Gmail Mailbox OAuth Redirects

For production mailbox connections, use an HTTPS redirect URI on the same
deployment host: `https://YOUR_DOMAIN/api/mailboxes/connect/callback`. Set
`AUTOREACH_PUBLIC_BASE_URL=https://YOUR_DOMAIN` when running behind a custom
domain or proxy so the API can reject localhost or foreign-host redirects.

---

## Pre-launch checklist

- [ ] `AUTOREACH_JWT_SECRET` is a strong random value (not the dev default)
- [ ] `AUTOREACH_SESSION_SECRET` is a strong random value
- [ ] `AUTOREACH_CREDENTIAL_ENCRYPTION_KEY` is a generated Fernet key
- [ ] `AUTOREACH_PUBLIC_BASE_URL` is set to the deployed HTTPS origin
- [ ] `AUTOREACH_ENABLE_CONSOLE=0`
- [ ] `AUTOREACH_RUNTIME_SMART_DISPATCH=1`
- [ ] Postgres provisioned, `DATABASE_URL` wired
- [ ] Redis provisioned, `REDIS_URL` wired
- [ ] Worker consumes `engine,maintenance,standard-agents`
- [ ] Google OAuth client created, redirect URI added
- [ ] `GEMINI_API_KEY` set
- [ ] `CALCOM_WEBHOOK_SECRET` set
- [ ] `AUTOREACH_PHOENIX_ENDPOINT` set if Phoenix is deployed
- [ ] `python3 scripts/live_ops_launch.py plan --base-url https://YOUR_DEPLOYED_URL --domain YOUR_DOMAIN --smoke-email YOUR_SMOKE_USER --strict` has no required failures
- [ ] Cockpit → Operations → Production Readiness shows no required failures, including deep DB/Redis/Celery worker probes
- [ ] React SPA built (`cd dashboard && npm run build`) — Render does this in buildCommand
- [ ] Run `python3 -m pytest tests` → 339 passing
- [ ] Run `python3 scripts/e2e_saas_smoke.py` → all green
- [ ] Run `python3 scripts/production_smoke.py --base-url https://YOUR_DEPLOYED_URL --email YOUR_SMOKE_USER --password YOUR_SMOKE_PASSWORD`

---

## Smoke-test after deploy

```bash
# Full deploy smoke gate. Creates the smoke user if needed, otherwise logs in.
python3 scripts/production_smoke.py \
  --base-url https://autoreach-web.onrender.com \
  --email smoke@yourdomain.com \
  --password 'Password1!' \
  --company 'Smoke Tenant' \
  --calcom-webhook-secret "$CALCOM_WEBHOOK_SECRET" \
  --exercise-scoped-booking-webhook \
  --secret-denylist "$AUTOREACH_JWT_SECRET,$AUTOREACH_SESSION_SECRET"

# Health
curl https://autoreach-web.onrender.com/healthz

# Readiness (safe for uptime monitors)
curl https://autoreach-web.onrender.com/readyz

# Deep readiness (also pings the live DB, Redis, and Celery worker queues)
curl https://autoreach-web.onrender.com/readyz?deep=true

# Signup
curl -X POST https://autoreach-web.onrender.com/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"you@co.com","password":"Password1!","company_name":"You Co"}'

# The dashboard:
open https://autoreach-web.onrender.com/app/
```

---

## Scaling notes

- Web is stateless → scale horizontally (more web dynos).
- Worker is stateless → scale horizontally (more worker dynos) for more send throughput.
- Postgres pooling is configured (`pool_size=5, max_overflow=10, pool_pre_ping=True`).
- Per-mailbox daily caps + warmup ramps protect sender reputation as you scale.
- For very large prospect lists, the contacts API uses keyset cursor pagination
  (constant-time at any depth).
