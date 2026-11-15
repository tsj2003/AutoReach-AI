# Attainly ↔ Gojiberry Full-Cycle wiring

Evidence for the Gojiberry contract is the existing REA capture in
`docs/GOJIBERRY_COMPLETE_REVERSE_ENGINEERING_SPEC.md` (Book I Evidence IDs
`ev_00da2fd2…`, `ev_7723dca1…`, plus `ext.gojiberry.ai` OpenAPI
`CreateAgentExternalDto` / `CreateCampaignExternalDto`). This pass did not
open a new native REA session: REA MCP tools are not in this Cursor agent,
and `npx rea-agents doctor --client cursor` failed on a Swift SDK mismatch
in the sandbox. Claims below are labeled **observation** (source or that
spec) vs **inference** (Attainly wiring we closed).

Gojiberry Full-Cycle invariant (**observation**, spec §2.1):

`List` → `SourceAgent` (`POST /v1/agent`, ICP titles + keywords) → `Campaign`
(`listIds`) → mailbox / LinkedIn seats. Event signals throttle **72h**. Dual-axis
score lives on the contact; Copilot Approve is `readyForCampaign: true`, not a
score gate. LinkedIn-first sequences skip remaining LI steps and run email when
the connection request cannot complete (`skipInvitationAfterDays`).

## Wiring table

| Gojiberry stage | Attainly file | Status before this pass | Status now |
|---|---|---|---|
| Website → ICP (`onboarding_website`) | `cockpit/api/onboarding.py`, `engine/llm/website_intake.py`, `dashboard/src/components/OnboardingWizard.jsx` | **exists** | **called** on Launch step 1 |
| List (campaign container) | `cockpit/api/campaigns.py` `POST /api/campaigns` | **exists** | **called** — Launch creates the campaign |
| SourceAgent people search | `engine/services/people_discovery.py`, `engine/services/apollo_spider_engine.py`, Celery `engine.discover_campaign_people` | **exists-but-not-called** on live Azure: web image queued the task; worker/beat were on an older image and never consumed `discover_campaign_people`. Contacts stayed empty. | **called** on Launch (`auto_discover_people: true`, cap 15–25). Worker/beat must share the web image. |
| 72h event-signal throttle | `engine/services/people_discovery.py` `EVENT_SIGNAL_THROTTLE` | **missing** as a stamp | **stamped** on `people_discovery.last_complete_at` (Launch / Find buyers still always run) |
| Dual-axis score | `engine/signals/scoring.py`, `engine/signals/catalog.py`, Contacts UI | **exists** | **display only**. `min_lead_score` default is 0.6 (was 1.0). Copilot Approve sets `score_gate: false`. A 3% score does not block send. |
| Waterfall enrich | `engine/enrichment/`, `cockpit/api/enrichment.py` | **exists** | **called** from Contacts enrich actions; SourceAgent also runs OSINT email resolve |
| Campaign sequence | `engine/agents/outbound_agent.py`, wizard `DEFAULT_SEQUENCE` | **exists-but-not-called** — Launch did not POST `sequence`, so the agent fell back to a single email template while the UI showed LinkedIn-first | **called** — Launch sends the sequence; with no LinkedIn seat, LI steps collapse to the first email step immediately |
| LinkedIn Voyager seat | `cockpit/api/linkedin.py`, `engine/dispatch/linkedin_provider.py` | **exists** | **called** only when a seat cookie exists. Otherwise skip-to-email. |
| Mailbox send (`emailSeat`) | `engine/adapters/email_gmail_real.py` `GmailMailer`, `engine/dispatch/provider.py`, `engine/dispatch/adapter.py` | **exists-but-not-called** from Copilot Approve (approve only flipped `approved`; beat had to pick it up). Worker image lagged web. Earlier logs: missing `refresh_token` on a mailbox. | **called** — Approve executes immediately through the tenant mailbox (`to_email` on the smart router). Do not revert mailbox OAuth. |
| Copilot Approve | `cockpit/api/campaigns.py` `POST …/approve-job`, `engine/runtime/runtime.py` `approve_job` | **exists** (state only) | **sends** now; response includes `sent` / `channel` / `error` |
| Worker / beat | `engine/worker/celery_app.py`, Azure `attainly-worker` / `attainly-beat` | **exists** but **wrong image** vs `attainly-web` | **same image** after this deploy; queues `engine,maintenance,standard-agents` |
| Contacts auto-found leads | `cockpit/api/contacts.py`, `dashboard/src/pages/Contacts.jsx` | **exists** but empty because SourceAgent never completed | **polls** queued/running discovery for 120s; CSV remains optional |

## What is now connected

1. **Launch Full-Cycle Agent** creates the campaign (List), stores ICP titles/keywords/sequence, and **enqueues SourceAgent** (`kickoff_campaign_people_discovery` → Celery `engine.discover_campaign_people` when `REDIS_URL` is set; inline in tests). Cap 15–25.
2. SourceAgent writes prospects onto **that** campaign. Contacts polls until they appear.
3. Outbound planner skips LinkedIn steps when no Voyager seat is connected and plans the email step immediately.
4. Copilot **Approve** is a send: `GmailMailer` via the connected mailbox. Dual-axis score is not a gate.

## Live Azure observation (2026-10-20)

- `attainly-web` image `mailbox-oauth-20261020182434`
- `attainly-worker` / `attainly-beat` image `attainly-live-20261020083833`
- Worker logs: `engine.tick_all_active` with `planned: 0`; no `engine.discover_campaign_people`; earlier `ValueError: missing fields refresh_token` on Gmail
- Env on all three: `AUTOREACH_RUNTIME_SMART_DISPATCH=1`, `AUTOREACH_GMAIL_DRY_RUN=0`, `REDIS_URL` set

**Inference:** empty Contacts + Approve no-op were integration skew (queue task the old worker did not register, approve waiting on beat, LinkedIn-first sequence with no seat), not a missing ICP or Gmail OAuth connect UI.

## What to do on the live app after deploy

1. Open Attainly → paste a website → **Launch Full-Cycle Agent**.
2. Open **Contacts** for that campaign. Wait for auto-found buyers (no CSV). Use **Find buyers from ICP** if the first run was queued on the old worker.
3. Confirm a Gmail mailbox is connected (Mailboxes). LinkedIn seat is optional.
4. Open the campaign **Actions** queue → **Approve**. That sends the email step through the connected mailbox. A low dual-axis score must not block it.
5. If Approve returns an error, it is a mailbox token/health problem (reconnect Gmail), not a silent no-op.
