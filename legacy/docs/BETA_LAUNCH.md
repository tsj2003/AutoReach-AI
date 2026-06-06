# AutoReach-AI — Beta Launch Checklist

## Pre-Launch: Google OAuth Testing Mode
1. Go to [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → OAuth consent screen
2. Set publishing status to **"Testing"**
3. Add up to 100 test user Gmail accounts under "Test users"
4. Verify that the OAuth consent screen shows your app name, logo, and links:
   - Privacy Policy: `https://YOUR_DOMAIN/privacy`
   - Terms of Service: `https://YOUR_DOMAIN/terms`
5. Scopes requested: `gmail.send`, `gmail.readonly`, `userinfo.email`, `postmaster.readonly`

## Pre-Launch: Razorpay Configuration
1. Use **Test Mode** API keys from [Razorpay Dashboard](https://dashboard.razorpay.com)
2. Set environment variables:
   - `RAZORPAY_KEY_ID=rzp_test_...`
   - `RAZORPAY_KEY_SECRET=...`
3. Verify all compliance pages are live:
   - `/privacy` — Privacy Policy
   - `/terms` — Terms of Service
   - `/refund-policy` — Refund & Cancellation Policy
   - `/contact` — Contact Us with physical address

## Pre-Launch: Environment Setup
```bash
# Copy and fill in environment variables
cp .env.example .env

# Required variables for beta:
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
SECRET_KEY=<random-64-char-string>
GOOGLE_CLIENT_ID=<from-google-console>
GOOGLE_CLIENT_SECRET=<from-google-console>
GEMINI_API_KEY=<your-key>
SENTRY_DSN=<from-sentry-dashboard>
POSTHOG_API_KEY=<from-posthog-settings>
APP_DOMAIN=your-domain.com
```

## Launch: Deploy to Render
1. Push code to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com)
3. Click "New" → "Blueprint" → select the repo
4. Render reads `render.yaml` and creates: web service, worker, PostgreSQL, Redis
5. Fill in environment variable values in the Render dashboard

## Post-Launch: Monitoring
- **Sentry**: [sentry.io](https://sentry.io) — check for unhandled exceptions in web + worker
- **PostHog**: [posthog.com](https://posthog.com) — track signup funnel, campaign starts, drop-offs
- **Render Logs**: Dashboard → Services → Logs tab

## Incident Response
1. **Worker crashed**: Check Render worker logs → Celery auto-retries 3x → Sentry alert fires
2. **All mailboxes quarantined**: Campaign auto-pauses → SMTP alert sent → user sees dashboard banner
3. **High spam rate (>0.15%)**: Campaign auto-pauses → Sentry + SMTP alert → review email content quality
4. **Database connection issues**: `pool_pre_ping=True` handles stale connections → Sentry alerts on persistent failures

## Dogfooding Campaign
1. Build a CSV with 200 founders/growth marketers from Apollo.io
2. Connect your own Google Workspace account via OAuth
3. Create campaign with Gemini personalization enabled
4. Use pitch: "Hey {first_name}, I built an autonomous outreach engine that wrote this exact email. It handles inbox rotation and deliverability defense. Want to try it for free?"
5. Monitor Postmaster Tools spam rate daily
