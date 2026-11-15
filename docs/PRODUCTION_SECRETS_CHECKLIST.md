# Production configuration activation — founder checklist

Use this only to unlock `/readyz?deep=true` on Azure. Do not paste secret values into chat, git, or tickets.

## Required exports (local shell)

```bash
export GEMINI_API_KEY='...'          # Google AI Studio
export GOOGLE_CLIENT_ID='...'        # Google Cloud → OAuth Web client
export GOOGLE_CLIENT_SECRET='...'
export CALCOM_WEBHOOK_SECRET='...'   # e.g. openssl rand -hex 32
```

## Google Cloud Console (Web OAuth client)

Authorized redirect URIs:

1. Primary (BYOC mailbox connect — required for next Gmail gate):
   `https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io/api/mailboxes/connect/callback`

2. Legacy operator console path (still mounted; register until deprecated):
   `https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io/oauth/google/callback`

## Cal.com webhook

- URL: `https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io/webhooks/calcom/booking`
- Secret: same value as `CALCOM_WEBHOOK_SECRET`
- Include tenant/campaign metadata in bookings so production matching stays scoped

## Apply (keeps Gmail dry-run; does not print secrets)

```bash
cd /Users/tarandeepsinghjuneja/AutoReach-AI
python3 scripts/azure_live_activation.py check   # must exit 0
python3 scripts/azure_live_activation.py apply   # web + worker + beat
python3 scripts/azure_live_activation.py verify  # Azure refs + healthz + deep readyz
```

Success: verify exits 0 and deep readyz reports `ok: true`, `missing_required: []`.

Then the next ladder step is Gmail live proof (still locked until verify passes).
