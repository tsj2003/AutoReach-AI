# DigitalOcean Deployment

Use DigitalOcean App Platform when you want a production-ish always-on launch
without Render free-tier cold starts. This deploy runs the same production shape:

- web: FastAPI + React Cockpit
- worker: Celery worker on `engine,maintenance,standard-agents`
- beat: Celery scheduler
- managed Postgres
- managed Redis

## 1. Prepare The Repo

Commit and push the repo to GitHub.

Update `.do/app.yaml`:

- replace `YOUR_GITHUB_OWNER/AutoReach-AI` with your real GitHub repo
- replace `https://REPLACE_WITH_YOUR_DO_APP_DOMAIN` after DigitalOcean gives you the app URL
- replace all `REPLACE_WITH_...` secrets or set them in the App Platform UI

Generate internal secrets:

```bash
python3 scripts/live_ops_launch.py generate-secrets --dotenv
```

Use those values for:

- `AUTOREACH_JWT_SECRET`
- `AUTOREACH_SESSION_SECRET`
- `AUTOREACH_CREDENTIAL_ENCRYPTION_KEY`
- `CALCOM_WEBHOOK_SECRET`

## 2. Create The App

Dashboard path:

1. DigitalOcean → App Platform → Create App
2. Import from GitHub
3. Choose this repo
4. Use/import `.do/app.yaml`
5. Confirm web, worker, beat, Postgres, and Redis components
6. Deploy

CLI path:

```bash
doctl apps create --spec .do/app.yaml
```

After the app is created, DigitalOcean assigns a default URL similar to:

```text
https://autoreach-ai-xxxxx.ondigitalocean.app
```

Set:

```bash
AUTOREACH_PUBLIC_BASE_URL=https://autoreach-ai-xxxxx.ondigitalocean.app
```

Then redeploy.

## 3. Required App Env Vars

These must be present before a real pilot:

```bash
DATABASE_URL=${autoreach-db.DATABASE_URL}
REDIS_URL=${autoreach-redis.REDIS_URL}
AUTOREACH_ENABLE_CONSOLE=0
AUTOREACH_RUNTIME_SMART_DISPATCH=1
AUTOREACH_WORKER_QUEUES=engine,maintenance,standard-agents
AUTOREACH_PUBLIC_BASE_URL=https://YOUR_DO_APP_DOMAIN
AUTOREACH_JWT_SECRET=...
AUTOREACH_SESSION_SECRET=...
AUTOREACH_CREDENTIAL_ENCRYPTION_KEY=...
GEMINI_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
CALCOM_WEBHOOK_SECRET=...
```

Optional but recommended:

```bash
AUTOREACH_PHOENIX_ENDPOINT=...
SENTRY_DSN=...
```

## 4. Google OAuth Redirect

Add this redirect URI in Google Cloud:

```text
https://YOUR_DO_APP_DOMAIN/api/mailboxes/connect/callback
```

If you use Google login, also ensure the login client ID is set through either:

```bash
GOOGLE_SIGNIN_CLIENT_ID=...
```

or let it fall back to:

```bash
GOOGLE_CLIENT_ID=...
```

## 5. Cal.com Webhook

In Cal.com, point the booking webhook at:

```text
https://YOUR_DO_APP_DOMAIN/webhooks/calcom/booking
```

Use the same secret as:

```bash
CALCOM_WEBHOOK_SECRET
```

Every booking link/campaign must include metadata:

- `tenant_id`
- `engagement_id` or `campaign_id`

## 6. Verify The Live App

Run:

```bash
export AUTOREACH_SMOKE_PASSWORD='choose-a-strong-smoke-password'

python3 scripts/live_ops_launch.py plan \
  --base-url https://YOUR_DO_APP_DOMAIN \
  --smoke-email smoke@example.com \
  --strict
```

Then run the deployed smoke test:

```bash
python3 scripts/production_smoke.py \
  --base-url https://YOUR_DO_APP_DOMAIN \
  --email smoke@example.com \
  --password "$AUTOREACH_SMOKE_PASSWORD" \
  --company 'Smoke Tenant' \
  --calcom-webhook-secret "$CALCOM_WEBHOOK_SECRET" \
  --exercise-scoped-booking-webhook \
  --secret-denylist "$AUTOREACH_JWT_SECRET,$AUTOREACH_SESSION_SECRET,$CALCOM_WEBHOOK_SECRET"
```

## 7. Cost/Scale Notes

For a public demo/pilot, keep all three components running:

- web: at least one always-on instance
- worker: at least one instance
- beat: one instance only

Do not run multiple beat instances unless you add distributed scheduler locking.

Managed Postgres and Redis should be used for real pilots. SQLite is only for
local/dev demos.
