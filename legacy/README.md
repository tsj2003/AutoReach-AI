# `legacy/` — pre-pivot AutoReach code

Everything here is from before the May 2026 pivot to the **AutoReach engine
+ cockpit** architecture. It's preserved for reference and for selectively
porting useful pieces, **not** for active development.

## What's here

```
legacy/
├── app/                          Flask SaaS shell (multi-user, Razorpay, Google OAuth)
│   ├── routes.py                 ~50k lines of Flask blueprint code
│   ├── models.py                 SQLAlchemy User/Campaign/Contact/Token models
│   ├── tasks.py                  Celery campaign batch tasks
│   ├── worker.py                 CampaignExecutor with the original Gmail send code
│   ├── celery_app.py             Celery factory
│   ├── services/                 dns_validator, postmaster, scrambler, notifications, analytics
│   ├── templates/                Jinja2 HTML templates (dashboard, login, signup, legal pages)
│   └── static/                   Compiled React SPA assets
│
├── scripts/                      Original CLI entry points
│   ├── bulk_mail_with_attachment.py   The original single-user Gmail sender
│   ├── cli_pro.py                Rich-based terminal UI
│   ├── quick_cli.py              Ultra-short CLI
│   ├── campaign_manager.py
│   ├── campaign_status.py
│   ├── utils.py
│   └── ...
│
├── deploy/                       Deployment config from the Flask era
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── Procfile
│   ├── render.yaml
│   └── celery_worker.py
│
├── data/                         Personal job-search artifacts
│   ├── out/                      Curated CSV queues
│   ├── campaigns/                Old YAML campaign configs
│   ├── templates/                Email Jinja templates (job-app + outreach)
│   └── ...
│
├── tests/                        Tests for the legacy Flask app
│   ├── test_dashboard.py
│   ├── test_features.py
│   ├── test_saas_features.py
│   ├── test_sequences.py
│   └── conftest.py
│
└── docs/                         Pre-pivot docs (mostly stale)
    ├── APP_CONTEXT.md            Out-of-date system overview
    ├── LAUNCH.md
    ├── BETA_LAUNCH.md            Operational playbook for the Flask SaaS
    ├── COMMANDS.md
    ├── QUICK_COMMANDS.md
    └── README_CAMPAIGN.md
```

## What's worth porting

When wiring real Gmail send + reply detection in Phase 3, the most useful
sources here are:

- `app/worker.py::CampaignExecutor._send_one` and the MIME builder — battle-tested
- `app/worker.py::personalize_with_gemini` — Gemini call structure
- `app/worker.py::classify_reply_with_gemini` and `generate_reply_draft_with_gemini`
- `app/worker.py::_check_replies` and `_scan_contacts_for_replies` — Gmail polling logic
- `app/services/dns_validator.py` — SPF/DKIM/DMARC checks
- `app/services/postmaster.py` — Google Postmaster Tools integration
- `app/services/scrambler.py` — Gemini structural rewriter

## What is *not* worth porting

- Anything in `app/routes.py` — too coupled to Flask + the multi-tenant SaaS shell.
  We're rebuilding the surface (cockpit/) cleanly.
- Anything Razorpay-related — pricing/billing belongs at a higher layer.
- The React SPA in `app/static/` — superseded by the cockpit's server-rendered HTML.

## Why archive instead of delete

Three reasons:

1. The Gmail OAuth + send + reply-detection code in `app/worker.py` is **real
   working code** with non-trivial edge-case handling. Phase 3 ports it cleanly
   into the new adapter shape; we'd be foolish to retype it.
2. `out/` contains personal job-application data that's `.gitignore`d. Keeping
   it under `legacy/` makes it explicit it's not part of the new product.
3. The old test suite (`test_saas_features.py`, etc.) covers behaviors we'll
   want to rebuild as engine integration tests in later phases — useful as a
   spec, not as runnable tests.

This directory is **not on the import path** for the new code. Nothing in
`engine/` or `cockpit/` imports from here.
