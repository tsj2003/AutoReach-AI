# Pilot Operations Runbook (v0)

Use with `docs/PILOT_READINESS_GATE.md`. This is an operational relationship checklist, not a feature list.

## Pre-flight (before inviting a pilot)

- [ ] `GET /healthz` → `ok: true`
- [ ] `GET /readyz` → `ok: true` (no placeholder JWT/session/Fernet)
- [ ] `GET /readyz?deep=true` → DB + Redis + Celery queues OK
- [ ] `GET /app/` → 200
- [ ] Legacy console disabled (`AUTOREACH_ENABLE_CONSOLE=0`)
- [ ] `AUTOREACH_GMAIL_DRY_RUN=0` only after a controlled mailbox is ready
- [ ] Enrichment off unless keys exist (`AUTOREACH_ENRICHMENT_ENABLED=0`)
- [ ] Learning off unless you want measurement API (`AUTOREACH_LEARNING_ENABLED=0`)
- [ ] Phoenix optional; if empty, rely on DO logs + Sentry if configured

## Kill switches (mandatory drill)

| Switch | How | Effect |
|--------|-----|--------|
| Pause campaign | `POST /api/campaigns/{id}/pause` | Runtime skips non-active campaigns |
| Resume campaign | `POST /api/campaigns/{id}/resume` | Back to active |
| Pause mailbox | `POST /api/mailboxes/{id}/pause` | Router will not select it |
| Resume mailbox | `POST /api/mailboxes/{id}/resume` | Status active |
| Stop all planning/sends | Set `AUTOREACH_ENGINE_PAUSED=1` on worker/beat | `tick_all_active` no-ops |
| Stop signal ingest | `AUTOREACH_SIGNALS_ENABLED=0` | API + beat ingest gated |
| Stop reply AI actions | `AUTOREACH_REPLY_AI_ENABLED=0` | Classify may still record; no auto actions |
| Gmail network stop | `AUTOREACH_GMAIL_DRY_RUN=1` | Adapter does not call Gmail send API |
| Scale-to-zero | DO: stop worker + beat | Hard stop (platform) |

## Mailbox setup

1. Configure Google OAuth client with redirect matching `AUTOREACH_PUBLIC_BASE_URL`.
2. Connect mailbox via dashboard Operations / Mailboxes.
3. Confirm status `active` and encrypted credentials stored.
4. Warmup / daily caps as per launch checklist.
5. First sends: controlled test recipient only.

## Campaign launch

1. Run `GET /api/operations/launch-checklist` (or UI equivalent).
2. Client cure + non-empty signal matrix required.
3. HITL threshold: prefer low (e.g. 1–10) for early pilot — do not rely on trust-ramp auto-send.
4. Approve first jobs manually; confirm Gmail message ids in events/job result.

## Incident response (founder on-call)

1. Pause affected campaign(s).
2. Pause affected mailbox(es).
3. Set `AUTOREACH_ENGINE_PAUSED=1` if blast radius unclear.
4. Capture: time, tenant_id, campaign_id, job_id, trace_id, provider error.
5. Check DO web/worker/beat logs for 5xx / Celery failures (HTTP 200 ≠ healthy workers).
6. Rotate credentials if token leak suspected.
7. Resume only after root cause + one controlled test send.

## Credential rotation

- JWT / session / Fernet: generate new values; update DO; redeploy; force re-login.
- Google OAuth client secret: update DO + local; reconnect mailboxes.
- Mailbox tokens: revoke + reconnect via OAuth flow.
- Webhook secrets: rotate per signal source; update senders.

## Unsubscribe / DNC

- Engine auto-stops sequences on unsubscribe / do_not_contact classifications.
- Prefer HITL for ambiguous replies during pilot.
- Modern public unsubscribe endpoint: still a follow-up (P2).

## Data / privacy (pilot)

- Store only what the pilot needs: prospects, drafts, replies, tokens, costs, signals.
- No cross-tenant queries without tenant_id filter.
- Tenant export / hard delete: not yet productized — handle manually with founder approval until export API exists.

## Success metric (first pilots)

Hypothesis: a founder-led B2B team can go from connected mailbox → approved send → classified reply within one working session, with zero cross-tenant incidents and a working pause drill.

Track: time-to-first-approved-send, reply classification accuracy (spot check), kill-switch drill pass/fail, willingness to continue week 2.
