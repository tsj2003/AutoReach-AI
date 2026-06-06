# AutoReach — Deployment Guide

Production deploy to Render (or any Docker host). Supersedes the legacy
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

## Deploy to Render (Blueprint)

1. Push the repo to GitHub.
2. Render Dashboard → **New → Blueprint** → select the repo.
3. Render reads `render.yaml` and provisions: web, worker, beat, Postgres, Redis.
4. Fill in the `sync: false` env vars in the dashboard:
   - `GEMINI_API_KEY`
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
   - `CALCOM_WEBHOOK_SECRET` (optional)
   - `SENTRY_DSN` (optional)
5. `AUTOREACH_JWT_SECRET` and `AUTOREACH_SESSION_SECRET` are auto-generated.
6. First deploy runs DB schema creation automatically (`metadata.create_all`).

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
| `GEMINI_API_KEY` | for AI | reply classification + personalization |
| `GOOGLE_CLIENT_ID` / `_SECRET` | for Gmail | OAuth mailbox connection |
| `CALCOM_WEBHOOK_SECRET` | optional | verifies Cal.com booking webhooks |
| `SENTRY_DSN` | optional | error monitoring |

---

## Pre-launch checklist

- [ ] `AUTOREACH_JWT_SECRET` is a strong random value (not the dev default)
- [ ] Postgres provisioned, `DATABASE_URL` wired
- [ ] Redis provisioned, `REDIS_URL` wired
- [ ] Google OAuth client created, redirect URI added
- [ ] `GEMINI_API_KEY` set
- [ ] React SPA built (`cd dashboard && npm run build`) — Render does this in buildCommand
- [ ] Run `PYTHONPATH=. python -m pytest tests/ -q` → 164 passing
- [ ] Run `PYTHONPATH=. python scripts/e2e_saas_smoke.py` → all green

---

## Smoke-test after deploy

```bash
# Health
curl https://autoreach-web.onrender.com/healthz

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
