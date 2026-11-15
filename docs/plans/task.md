| id | task | status | notes |
| --- | --- | --- | --- |
| t1-t13 | Previous SaaS features (persistence, quarantine, tests) | completed | 17/17 tests pass |
| p1a-1 | Update requirements.txt with production deps | completed | psycopg2, celery, redis, sentry, posthog, gunicorn, dotenv, dnspython |
| p1a-2 | Create `.env.example` template | completed | All env vars documented |
| p1a-3 | Update `app/__init__.py` for PostgreSQL + Sentry + dotenv | completed | postgres:// rewrite, pooling, Sentry init |
| p1a-4 | Create SQLite→PostgreSQL migration script | deferred | Manual step for production — no local Postgres to test |
| p1b-1 | Create `app/celery_app.py` Celery factory | completed | Redis broker, Flask context binding, task routing |
| p1b-2 | Create `app/tasks.py` Celery tasks | completed | Campaign batch, reply check, daily counter reset |
| p1b-3 | Update `app/worker.py` CampaignExecutor | completed | Auto-detects Redis: Celery in prod, threads in dev |
| p1b-4 | Create `celery_worker.py` entrypoint | completed | Flask+Celery bootstrap |
| p1c-1 | Create `Procfile` for Render | completed | web, worker, beat processes |
| p1c-2 | Create `Dockerfile` | completed | Multi-stage Python build |
| p1c-3 | Create `docker-compose.yml` for local dev | completed | 5 services: web, worker, beat, redis, postgres |
| p1c-4 | Create `render.yaml` blueprint | completed | Declarative Render deployment |
| p2a-1 | Create legal templates (privacy, terms) | completed | Public privacy policy & ToS pages — 200 OK verified |
| p2a-2 | Add legal page routes to `app/routes.py` | completed | GET /privacy, /terms, /refund-policy, /contact |
| p2a-3 | Update landing page footer with legal links | completed | Privacy, Terms, Refund, Contact links |
| p2b-1 | Create refund policy and contact page templates | completed | Razorpay compliance pages — 200 OK verified |
| p3a-1 | Integrate Sentry SDK in `app/__init__.py` | completed | Flask + Celery + SQLAlchemy integrations |
| p3b-1 | Create `app/services/analytics.py` PostHog wrapper | completed | Lazy init, silent no-op if unconfigured |
| p3b-2 | Add PostHog tracking calls to routes | completed | user_signed_up, user_logged_in events |
| p5a-1 | Add `unsubscribe_token` to Contact model | completed | secrets.token_urlsafe(32), unique column |
| p5a-2 | Create unsubscribe endpoints in routes.py | completed | POST + GET /api/unsubscribe/<token> |
| p5a-3 | Inject RFC 8058 headers in worker.py MIME build | completed | List-Unsubscribe + List-Unsubscribe-Post |
| p5a-4 | Create unsubscribe.html template | completed | Branded confirmation page with masked email |
| p5b-1 | Create `app/services/dns_validator.py` | completed | SPF, DKIM, DMARC checks with copy-paste fix instructions |
| p5b-2 | Add DNS check endpoint + campaign gate | completed | GET /api/dns-check returns validation result |
| p5c-1 | Create `app/services/postmaster.py` | completed | Google Postmaster Tools API client |
| p5c-2 | Expand OAuth scopes for Postmaster | completed | Added postmaster.readonly scope |
| p5c-3 | Add spam rate check to worker loop | deferred | Requires Postmaster API integration in campaign loop |
| p5d-1 | Create `app/services/scrambler.py` | completed | Gemini structure rewriter, 0.85 temp, safety fallback |
| p5d-2 | Integrate scrambler into worker pipeline | completed | Post-personalization, pre-MIME step |
| p4-1 | Create `BETA_LAUNCH.md` checklist | completed | Full operational playbook |
| final | Run full test suite and verify | completed | 17/17 tests pass (including Playwright E2E tests) |
| p6-1 | Build React + Tailwind WisprFlow-style landing page | completed | Exact font pairings, Rive audio animation, and asset copy pipeline integrated in Flask |
| p6-2 | Polish landing page with Framer Motion micro-interactions & spacing | completed | Antialiased font smoothing, hover glows/lifts, py-32 and p-8 padding, max-w-6xl limits |
| p6-3 | Re-theme login, signup and unsubscribe templates | completed | Implemented DM Serif Display + Inter, radial purple glows, scaling hover/click states |
| p6-4 | Re-theme legal compliance pages | completed | Updated privacy, terms, refund, contact pages with theme coherence |
| p6-5 | Re-theme cockpit dashboard.html | completed | Swapped configuration variables, fonts, text readability, button animations |
| p6-6 | Verify pages load and run all tests | completed | 17/17 pytest suite runs completed with success |
| p6-7 | Clean up hardcoded purple colors in App.jsx | completed | Replace with green/emerald variants |
| p6-8 | Implement OrganicWaveVisualizer canvas component | completed | Overlapping bezier morphing waves in Hero |
| p6-9 | Compile React landing page | completed | Run npm run build |
| p6-10 | Copy React build assets to app/static/assets/ | completed | Deploy production assets |
| p6-11 | Update landing.html and run verification check | completed | Verify design loads & all tests pass |
| p7-1 | Redesign index.css design tokens for cream & lavender theme | completed | Set background-color to #FAF8F5, text color, and buttons shadow |
| p7-2 | Implement SVG-based moving CurvedTextPath in App.jsx | completed | Wavy text path with infinite CSS/SVG animation |
| p7-3 | Implement parabolic CurvedIconMarquee arch | completed | Animated floating icon arc |
| p7-4 | Build Jordan chat simulation & active soundwave visualizer | completed | Live mockup demo inside phone widget |
| p7-5 | Re-compile and deploy all visual updates | completed | Ran npm run build & copied production assets |
| p8-1 | Modify Flask routes to serve landing.html for GET paths | completed | Done in routes.py |
| p8-2 | Inject FLASK_ERROR and UNSUBSCRIBE_EMAIL in landing.html | completed | Done in landing.html |
| p8-3 | Implement client-side routing in React App.jsx | completed | Router based on window.location.pathname |
| p8-4 | Build React Login and Signup pages in App.jsx | completed | Center cards with form inputs & Flask error bindings |
| p8-5 | Build React Unsubscribe and Legal pages in App.jsx | completed | Layout templates and policies viewer |
| p8-6 | Build React SaaS Dashboard Cockpit (all 4 tabs & APIs) in App.jsx | completed | Campaigns, steps, inboxes, logs, AI reply drafts |
| p8-7 | Compile and copy built SPA assets to Flask static | completed | Production build compiled directly to app/static/assets |
| p8-8 | Verify and run backend pytest suite | completed | All 17 tests (including E2E Playwright dashboard and tabs) pass successfully |
| p9-1 | Extract and clean HR contacts CSV from Downloads | completed | Validated, unique, 100 target list |
| p9-2 | Write cleaned batch of 100 to newlit.csv | completed | 100 contacts written to newlit.csv |
| p9-3 | Plan and schedule email send jobs with random 1-2 min delays in DB | completed | 100 jobs planned in SQLite with random spacing |
| p9-4 | Run dry-run simulation of the HR outreach campaign | completed | Previews generated and verified successfully |
| p9-5 | Execute live sending campaign | in_progress | Campaign running in background |




