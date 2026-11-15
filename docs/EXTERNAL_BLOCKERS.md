# External blockers — exact actions (Final Master Loop)

Re-verified: 2026-09-03. Do not treat this as living production health without re-running the commands.

---

## BLOCKER 1 — Production DNS / reachable deploy

**Why:** Hostname in `.do/app.yaml` does not resolve from this environment.

**Hostname assumed:** `https://autoreach-ai-j2rdy.ondigitalocean.app`

**External action required:**
1. Open DigitalOcean App Platform → app `autoreach-ai`.
2. Confirm the app still exists and has a live default ingress URL (it may have been renamed/destroyed).
3. If destroyed: redeploy from `.do/app.yaml` / GitHub `main`.
4. Update `AUTOREACH_PUBLIC_BASE_URL` in DO and Google OAuth redirect URIs to the live URL.
5. If using a custom domain: add DO-managed DNS A/CNAME records and wait for propagation.

**Verification:**
```bash
dig +short autoreach-ai-j2rdy.ondigitalocean.app A
curl -sS https://autoreach-ai-j2rdy.ondigitalocean.app/healthz
curl -sS 'https://autoreach-ai-j2rdy.ondigitalocean.app/readyz?deep=true'
curl -sS -o /dev/null -w '%{http_code}\n' https://autoreach-ai-j2rdy.ondigitalocean.app/app/
```

**Success:** DNS returns IPs; healthz `ok:true`; deep readyz `ok:true` with DB/Redis/Celery queues; `/app/` HTTP 200.

**This environment:** `curl: (6) Could not resolve host`. `doctl apps list` → Forbidden (no DO API token in this session).

---

## BLOCKER 2 — Production secrets not placeholder

**Why:** `.do/app.yaml` still ships `REPLACE_WITH_*` for JWT, session, Fernet, Gemini, Google OAuth, Cal.com.

**External action:** In DO App Settings → App-Level / component env, set real SECRET values (do not leave YAML placeholders). Generate Fernet:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Verification:**
```bash
curl -sS 'https://<LIVE_HOST>/readyz' | python3 -m json.tool
# missing_required must be []
# jwt_secret / session / encryption must not appear as failed
```

**Success:** `/readyz` → `ok: true` and no placeholder-related failures.

---

## BLOCKER 3 — Controlled Gmail mailbox + live send

**Why:** No production mailbox path verified. Local `.env` has `AUTOREACH_GMAIL_SENDER=you@yourdomain.com` (placeholder) and `AUTOREACH_GMAIL_DRY_RUN=1`. `token.json` exists but is not a tenant-scoped production mailbox.

**External action:**
1. Create/use a controlled Google Workspace or Gmail mailbox you own.
2. Configure Google OAuth client with redirect `https://<LIVE_HOST>/api/mailboxes/connect/callback`.
3. Set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in DO.
4. Sign into pilot tenant → Operations → Mailboxes → Connect Gmail.
5. Set `AUTOREACH_GMAIL_DRY_RUN=0` on web/worker only after connect succeeds.
6. Send to a test recipient you control.

**Verification:**
```bash
python3 scripts/gmail_proof_chain.py --tenant-id <pilot_tenant_id> --live --json
# Then: approve an outbound job via API/UI and confirm Gmail message id in job.result / events
```

**Success:** Provider returns `gmail_message_id`; job state `succeeded`; reply never marked sent before provider confirmation.

---

## BLOCKER 4 — Real reply detect → classify → approve → send

**Why:** Depends on Blocker 3. Unit-tested only.

**External action:** Reply from the controlled recipient to the proof message; run Poll replies; approve AI draft; confirm second Gmail send id.

**Success:** Reply row persisted with classification; approve returns `sent:true` with provider confirmation; idempotent re-approve does not double-send.

---

## BLOCKER 5 — Hunter live enrichment

**Why:** Code is real; this environment has `HUNTER_API_KEY=MISSING`. Flag `AUTOREACH_ENRICHMENT_ENABLED` defaults off.

**External action:** Set `HUNTER_API_KEY` and `AUTOREACH_ENRICHMENT_ENABLED=1` in local/DO env.

**Verification:**
```bash
export HUNTER_API_KEY=... AUTOREACH_ENRICHMENT_ENABLED=1
pytest -m integration tests/test_hunter_enrichment.py::test_hunter_live_smoke_when_key_present -q
# or POST /api/enrichment/prospect/{id} for a no-email prospect with company domain
```

**Success:** Response has email + provenance provider=hunter; prospect.research.enrichment persisted; without key remains `CONFIGURATION_REQUIRED` / NOT_CONFIGURED.

---

## BLOCKER 6 — Worker/beat live queues

**Why:** Deep readyz cannot be checked while DNS is down. Code schedules `tick_all_active` + signal ingest.

**External action:** After DNS works, ensure DO services `autoreach-worker` and `autoreach-beat` are running (exactly one beat).

**Verification:** `GET /readyz?deep=true` shows Celery queues `engine,maintenance,standard-agents` consumed.

---

## Not blockers for pilot v0 (intentionally deferred)

- Clearbit / Apollo (explicit stubs)
- CRM MCP writes
- Autonomous learning / prompt mutation
- Outlook send parity
- Intent Kafka/dlt bridge
