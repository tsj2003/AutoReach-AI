# Attainly — Final Pilot Readiness Gate

**Date:** 2026-09-03 (updated after Master Loop Phase A–E code)
**Decision:** **NO-GO** for controlled pilot

## Phase D live proof (this environment)

| Check | Result |
|-------|--------|
| DNS `autoreach-ai-j2rdy.ondigitalocean.app` | FAIL — resolve/timeout |
| `/healthz` | FAIL — unreachable |
| Live Gmail proof | NOT RUN — no reachable deploy + controlled mailbox tenant |
| Kill-switch drill on live app | NOT RUN |

**External dependency to close Phase D:** Restore DO App Platform DNS + confirm secrets + connect controlled Gmail mailbox + run `scripts/gmail_proof_chain.py --live --tenant-id …`.

## Code closed in Master Loop (Phases A–C, E)

- Contactable prospect required on launch checklist
- Manual contact add + contact counts UI
- Lead scrape UI on Campaign Detail
- Website subject/body templates → agent config
- Campaign/mailbox pause UI + Mailboxes page
- Inbox “Approve & send”
- Plan lead caps enforced
- Hunter.io real provider (NOT_CONFIGURED without key) + prospect write-back
- Account entity (domain-keyed) + API/UI
- Learning recommendations advisory-only (no auto mutation)

## GO criteria still failing

1. Controlled production deployment
2. Real mailbox send verified
3. Core revenue loop live-verified

See prior sections for full matrix. Ops checklist: `docs/PILOT_OPS_RUNBOOK.md`.

---

## 1. Verification layers (do not collapse)

| Layer | What it proves | Status this gate |
|-------|----------------|------------------|
| LOCAL VERIFIED | Unit/integration tests, imports, local TestClient | YES — green default suite |
| CI VERIFIED | GitHub Actions on Postgres+Redis | NOT RE-RUN this session |
| INTEGRATION VERIFIED | MCP stdio ClientSession (`-m integration`) | YES (local subprocess) |
| LIVE EXTERNAL SERVICE VERIFIED | Real Gmail API / Gemini / Cal.com | **NO** — Gmail dry-run only; no live send |
| PRODUCTION DEPLOYED | HTTP against live DO URL | **NO** — DNS `autoreach-ai-j2rdy.ondigitalocean.app` does not resolve from this environment |
| END-TO-END CUSTOMER VERIFIED | Real prospect → meeting → ROI | **NO** |

---

## 2. GO criteria vs reality

| # | Required for GO | Status |
|---|-----------------|--------|
| 1 | No unresolved critical security issue | LOCAL PASS (tests); prod secrets unverified |
| 2 | Controlled production deployment | **FAIL** — host DNS unresolved |
| 3 | Tenant isolation verified | LOCAL PASS (`tests/test_tenant_isolation_attack.py`) |
| 4 | Real mailbox integration verified | **FAIL** — needs tenant mailbox on live DB |
| 5 | Real send verified (provider message id) | **FAIL** |
| 6 | Core revenue loop verified | **FAIL** — loop not live E2E |
| 7 | Rollback/pause mechanism verified | CODE FIXED this gate; not live-drilled |
| 8 | Monitoring verified | **FAIL** — Phoenix empty; no deploy logs |
| 9 | Truthful product claims | PARTIAL — high-impact landing copy corrected |
| 10 | Documented pilot procedure | PARTIAL — see `docs/PILOT_OPS_RUNBOOK.md` |

**One critical failure ⇒ NO-GO.**

---

## 3. Pilot blocker list

### P0 — blocks customer safety

| Blocker | Evidence | Owner / dependency | Fixable in code? | Exact verification |
|---------|----------|--------------------|------------------|--------------------|
| Production JWT/session/Fernet may still be `REPLACE_WITH_*` in DO if dashboard never overridden | `.do/app.yaml` placeholders | Founder + DO secrets | No — must set live secrets | `GET /readyz` returns `ok:true` with no jwt/session/fernet in `missing_required` |
| Live production unreachable | `curl` DNS failure for `autoreach-ai-j2rdy.ondigitalocean.app` | DO App / DNS | No | Resolve DNS; `/healthz` + `/readyz?deep=true` + `/app/` 200 |
| OAuth mailbox tokens on disk (`token.json`, `credentials.json`) | Present locally, gitignored | Founder | Ops — rotate if ever shared | Confirm not in git history; rotate Google client secrets if exposed |

### P1 — blocks successful pilot

| Blocker | Evidence | Owner / dependency | Fixable in code? | Exact verification |
|---------|----------|--------------------|------------------|--------------------|
| Gmail send not live-proven | `scripts/gmail_proof_chain.py` without tenant → PARTIAL; no Gmail message id | Valid Google OAuth + controlled mailbox + test recipient | Partial (script exists) | Live proof: OAuth → approve → send → `gmail_message_id` persisted |
| Reply receive/classify/approve/send not live-proven | Unit-tested only | Same mailbox | No without mailbox | Controlled inbound reply → classify → approve → reply send id |
| End-to-end revenue loop unbroken | Subsystems exist; no recorded chain | Founder pilot tenant | No without providers | One full loop doc with INPUT/ACTION/OUTPUT/STATE per step |
| Celery worker+beat live queues | deep readyz unverified | DO worker/beat | No | `/readyz?deep=true` shows queues consumed |
| Phoenix / ops monitoring | `AUTOREACH_PHOENIX_ENDPOINT=""` | Optional Phoenix | Config | Either configure + export one span, or accept “no live observability” and monitor DO logs |
| Intent pipeline not E2E | No dlt/Kafka bridge; DuckDB path empty | Data pipeline | Yes later | Do not sell “intent auto-ingest” until wired |
| CRM MCP external | Fail-closed without server | External MCP CRM | No | Explicitly out of pilot scope |
| Paid enrichment | NotConfigured stubs | API keys | Config | Keep `AUTOREACH_ENRICHMENT_ENABLED=0` unless keys exist |

### P2 — important but can follow pilot

| Blocker | Evidence | Notes |
|---------|----------|-------|
| Tenant data export / offboarding API | Missing | Build before paid conversion |
| Public one-click unsubscribe in modern app | Legacy only | Port before volume |
| Incident runbook depth | Added skeleton this gate | Expand with on-call contacts |
| Outlook as send peer | Not implemented | Do not market |
| CampaignLearningEngine | Unwired | Keep off |
| Load/scale beyond pilot | Untested | Cap tenants intentionally |

---

## 4. What was closed in code this gate

| Change | Why |
|--------|-----|
| `AUTOREACH_ENGINE_PAUSED` gates `tick_all_active` | Global send/plan kill switch |
| `POST /api/campaigns/{id}/pause\|resume` | Per-campaign kill switch |
| `POST /api/mailboxes/{id}/pause\|resume` | Per-mailbox kill switch |
| Enrichment / learning APIs honor feature flags (default OFF) | Prevent half-built surfaces in pilot |
| Reply automation respects `AUTOREACH_REPLY_AI_ENABLED` | AI reply action kill switch |
| Landing / signup / personas / testimonials copy honesty pass | Remove autopilot / ∞ / 100k+ / “Backed by” / Primary guarantee / Outlook parity oversell |
| `tests/test_pilot_kill_switches.py` | Regression for pause + flags |

---

## 5. Security final gate (local)

| Check | Evidence | Result |
|-------|----------|--------|
| Tenant isolation attack suite | `tests/test_tenant_isolation_attack.py` | LOCAL VERIFIED |
| Webhook HMAC + replay | `tests/test_webhook_replay.py` | LOCAL VERIFIED |
| MCP auth / stdio handshake | `tests/test_mcp_handshake.py` (+ integration) | LOCAL / INTEGRATION |
| Secret redaction | `tests/test_secret_redaction.py` | LOCAL VERIFIED |
| Auth rate limit | `tests/test_auth_rate_limit.py` | LOCAL VERIFIED |
| Legacy console off in prod-like | readiness + `.do/app.yaml` | CONFIG — not live-proven |
| Production placeholders | YAML still has REPLACE_WITH_* | **OPEN until DO override proven** |
| Live cross-tenant against production DB | Requires deploy | **NOT DONE** |

---

## 6. Gmail production proof

**Status:** NOT COMPLETE

Local artifacts: `credentials.json`, `token.json`, `AUTOREACH_GMAIL_DRY_RUN=1` in env.

| Step | Status |
|------|--------|
| Controlled tenant + mailbox | NOT RUN (no `--tenant-id` / live DB mailbox) |
| OAuth token retrieval | Config-dependent local files only |
| Human approval → deterministic send job | Code YES (`reply_send_{id}`) |
| Gmail API confirmed send | **NO** |
| Reply poll → classify → approve → send | **NO** |

**Required for complete:** Valid OAuth for a **controlled** mailbox, a **test recipient you own**, `AUTOREACH_GMAIL_DRY_RUN=0`, and:

```bash
python3 scripts/gmail_proof_chain.py --tenant-id <pilot_tenant> --live --json
```

Never test against a real customer contact list.

---

## 7. Deployment proof

```text
curl https://autoreach-ai-j2rdy.ondigitalocean.app/healthz
→ Could not resolve host (2026-09-03, this environment)
```

Until DNS resolves and deep readyz passes, **production is not proven healthy** — regardless of App Platform “deployed” history.

---

## 8. End-to-end revenue loop (honest)

| Step | Code | Live proof |
|------|------|------------|
| Business setup / ICP / client cure / signal matrix | YES | NO on prod |
| Signal source → normalized → prospect | YES (matrix fail-closed) | NO full live chain |
| Enrichment | Partial (flagged off; paid stubs) | N/A |
| Draft → HITL → send | YES | NO live Gmail |
| Reply → classify → draft → approve → send | YES | NO live |
| Meeting → CRM → cost → ROI | Partial (CRM blocked; ledger real if meetings real) | NO |

**Any broken live link = pilot blocker.** Subsystem existence ≠ loop proof.

---

## 9. Readiness matrix

| CATEGORY | STATUS | EVIDENCE | BLOCKER | NEXT ACTION |
|----------|--------|----------|---------|-------------|
| Security | LOCAL PASS / PROD UNKNOWN | attack + webhook tests | Prod secret override | Live `/readyz` |
| Tenant isolation | LOCAL PASS | isolation tests | Live probe | Repeat on prod with 2 tenants |
| Authentication | LOCAL PASS | auth + rate limit tests | Prod JWT secret | Confirm not placeholder |
| Mailbox | PARTIAL | connect API + pause API | Live OAuth | Connect controlled mailbox |
| Gmail sending | CODE YES | adapter + idempotency | Live message id | Controlled live send |
| Signals | LOCAL PASS | registry + webhook + RSS | Prod DNS | Enable after deploy |
| Enrichment | OFF by default | flag gate | Keys | Keep off for pilot v0 |
| AI | CONFIG DEPENDENT | Gemini + fallback | Key + quality | Set Gemini on DO |
| Reply intelligence | LOCAL PASS | classifier tests | Live poll | Mailbox proof |
| MCP | PARTIAL | stdio tools read-only | Business ops live | Optional for pilot v0 |
| CRM | BLOCKED | fail-closed | External server | Out of scope |
| Billing | LOCAL PASS | Razorpay + plans | Live payment optional | Trial without card OK |
| ROI | PARTIAL | ledger | Real meetings | Only after meetings exist |
| Telemetry | PARTIAL | trace IDs; Phoenix empty | Endpoint | DO logs minimum |
| Workers | CODE YES | celery app | Live queues | deep readyz |
| Deployment | FAIL | DNS | DNS/app | Restore public URL |
| UX claims | IMPROVED | landing honesty pass | Rebuild static bundle | `npm run build` → ship |
| Onboarding | EXISTS | pilot-onboarding API | Live drill | Run checklist |
| Documentation | PARTIAL | this gate + ops runbook | — | Keep updating |
| Support | PARTIAL | kill switches | On-call | Assign founder as on-call |
| Privacy | PARTIAL | tenant scoped | Export/delete | Pre-paid |

---

## 10. What each layer can prove

| Layer | Can prove | Cannot prove |
|-------|-----------|--------------|
| CODE | Invariants, fail-closed paths, kill switches | Customers will use it |
| TESTS | Regressions, isolation, contracts | Live Gmail / DNS / DO secrets |
| LIVE ENV | Deploy health, OAuth, send ids, worker queues | Willingness to pay |
| REAL CUSTOMER | Retention, ROI, repeat meetings | — |

---

## 11. Smallest path to GO

1. **Restore / confirm production DNS** and pass `/healthz`, `/readyz`, `/readyz?deep=true`, `/app/`.
2. **Confirm DO secrets** are real (not YAML placeholders); rotate if unsure.
3. **Create isolated pilot tenant** + connect **one controlled Gmail mailbox**.
4. **Live Gmail proof chain** with a test recipient you own (send + reply + classify + approve + reply send).
5. **Record one full revenue-loop evidence** (even if CRM skipped).
6. **Rebuild dashboard static assets** so honest landing copy is what production serves.
7. **Drill kill switches** on the live app (pause campaign, pause mailbox, `AUTOREACH_ENGINE_PAUSED=1`).
8. Keep enrichment/CRM/learning/MCP mutation **out of scope** for pilot v0.

Do **not** expand features until the above are green.
