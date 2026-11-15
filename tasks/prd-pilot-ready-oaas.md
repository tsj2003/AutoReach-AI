# Pilot-Ready OaaS Console PRD

## Objective
Make AutoReach usable by an internal operator for the first 10 high-ACV customers without exposing unsafe self-serve controls.

## Stories

1. **Deliverability-gated tenant onboarding**
   - Operator can register a pilot tenant with budget, meeting price, LinkedIn, and MCP config.
   - Backend verifies SPF and DMARC before returning `ACTIVE`.
   - Unsafe tenants are saved as `PENDING_REMEDIATION`.
   - Status: done.

2. **Operator onboarding UI**
   - Cockpit has an operations page for creating pilot tenants.
   - Page shows preflight failures clearly and preserves the submitted economics.
   - Status: done.

3. **Pilot campaign launch checklist**
   - Campaigns cannot be activated without mailbox, DNS, budget, signal matrix, and approval queue checks.
   - Status: done.

4. **Daily operator mission control**
   - One view for pending approvals, burned inboxes, booked meetings, CRM sync failures, and budget risk.
   - Status: done.

5. **Customer proof package**
   - One-click ROI summary for a pilot customer: COGS, revenue, margin, trace IDs, outcomes, and CRM sync status.
   - Status: done.

6. **Production readiness gate**
   - Operator can see missing production secrets/services before onboarding paid pilots.
   - Web and worker initialize Phoenix telemetry from environment configuration.
   - Render worker consumes the `standard-agents` queue used by HITL approvals.
   - Status: done.

7. **Pre-pilot E2E smoke command**
   - One local command proves signup, campaign creation, readiness, launch checklist, HITL approval, reply, meeting qualification, analytics, mission control, proof package, tenant isolation, and SPA serving.
   - Status: done.

8. **Deploy readiness probe**
   - `/healthz` remains liveness.
   - `/readyz` exposes a safe production readiness summary for uptime monitors.
   - Status: done.

9. **First-class cure and signal matrix configuration**
   - Campaign API and Cockpit UI capture the specific client cure and allowed intent signal types.
   - Launch checklist enforces both, so operators can configure a launchable campaign without direct database edits.
   - Status: done.

10. **Campaign DNS preflight through product APIs**
    - Operators can run campaign-level SPF/DMARC preflight from the Cockpit campaign page.
    - The operations API persists the tenant-scoped preflight result into campaign metadata.
    - The launch checklist consumes the persisted result without direct database edits.
    - Status: done.

11. **Deep production dependency readiness**
    - `/readyz?deep=true` and the Operations readiness panel can run live database, Redis, and Celery worker queue probes.
    - The app factory defaults to `DATABASE_URL` before local `AUTOREACH_DB` so web and worker processes use the same production database source.
    - Probe results never expose connection strings, passwords, API keys, or secret values.
    - Status: done.

12. **Live deployed production smoke gate**
    - A single command can validate a deployed AutoReach URL with health, shallow readiness, deep readiness, authentication, operations readiness, and SPA serving checks.
    - The smoke command falls back to login when the smoke user already exists.
    - The smoke command fails if configured secret denylist values appear in responses.
    - Status: done.

13. **Public attack-surface deploy gate**
    - The live production smoke command verifies the unauthenticated legacy console, interactive docs, OpenAPI schema, and Operations readiness endpoint are not publicly reachable.
    - The FastAPI app disables `/openapi.json` alongside `/docs` and `/redoc`.
    - Status: done.

14. **Health-gated approved email dispatch**
    - Approved HITL outbox jobs are registered as a real Celery task on the `standard-agents` queue.
    - The dispatch task selects a healthy tenant mailbox through `SmartInboxRouter`.
    - The provider sends through the DB-token-backed Gmail adapter and fails closed when no healthy mailbox is available.
    - Status: done.

15. **Smart runtime email dispatch for legacy campaign jobs**
    - Production can set `AUTOREACH_RUNTIME_SMART_DISPATCH=1` so `EngineRuntime` email jobs use the same health-gated tenant mailbox router.
    - The runtime adapter resolves tenant ownership from storage instead of trusting the public engagement dataclass.
    - Production readiness fails when the smart runtime dispatch flag is not enabled.
    - Status: done.

16. **Engagement-scoped Celery ticks**
    - `engine.tick_engagement` now calls `runtime.tick(engagement_id=...)` instead of ticking all active campaigns.
    - A production wiring test prevents the scoped task from regressing back to global execution.
    - Status: done.

17. **Tenant-mailbox Gmail reply polling**
    - Smart-dispatch deployments build a tenant mailbox reply detector instead of relying on global Gmail token files.
    - Reply polling uses connected mailbox credentials via `DbTokenStore`.
    - Thread polling filters by mailbox ID so one tenant mailbox does not scan another mailbox's sent threads.
    - Status: done.

18. **Legacy bypass hardening**
    - Legacy Jinja console tick/drain controls now pass the current `engagement_id` into the runtime instead of running global loops.
    - `python -m engine tick` and `python -m engine drain` accept an optional `--engagement` scope for safer operator recovery.
    - One-off direct Gmail scripts no longer hardcode personal sender/token paths and require `AUTOREACH_ALLOW_LEGACY_DIRECT_SEND=1` before live sending.
    - Status: done.

19. **Legacy global OAuth closure**
    - Legacy `/oauth/google/start` and `/oauth/status` token-file routes now follow the legacy console gate instead of being mounted in production by default.
    - Tenant mailbox connection remains available through JWT-protected `/api/mailboxes` routes.
    - The live production smoke command fails if the legacy global OAuth routes are publicly reachable.
    - Status: done.

20. **Production-required booking webhook signatures**
    - Cal.com booking webhooks now fail closed in production mode unless `CALCOM_WEBHOOK_SECRET` is configured.
    - Invalid Cal.com signatures are rejected before payload processing.
    - Production readiness treats the Cal.com webhook secret as required.
    - Status: done.

21. **Mailbox credential encryption at rest**
    - Mailbox OAuth credential blobs and OAuth client secrets are encrypted before storage when `AUTOREACH_CREDENTIAL_ENCRYPTION_KEY` is configured.
    - Existing plaintext development rows remain readable for backward compatibility.
    - Production readiness requires a valid Fernet credential encryption key before pilot launch.
    - Status: done.

22. **Unsigned booking webhook live deploy probe**
    - The live production smoke command now sends an unsigned Cal.com booking webhook probe.
    - The smoke command fails unless the deployed webhook rejects the unsigned payload with an auth/configuration error.
    - Status: done.

23. **Global mailbox maintenance across tenants**
    - Storage now exposes a global mailbox iterator for maintenance workloads.
    - Daily send cap reset no longer depends on tenants having engagements.
    - Mailbox warmup advancement no longer depends on tenants having engagements.
    - Status: done.

24. **Tenant-scoped booking webhook matching**
    - Production Cal.com booking webhooks now require tenant or campaign scope before mutating meeting state.
    - Scoped payload metadata constrains prospect matching to the intended tenant/campaign.
    - Email-only global matching remains available only for local/dev unless explicitly re-enabled.
    - Status: done.

25. **Signed booking webhook live deploy probe**
    - The live production smoke command can now send a correctly signed Cal.com webhook probe when `--calcom-webhook-secret` is supplied.
    - The signed probe fails if the deployed endpoint rejects a valid signature or unexpectedly matches a real booking.
    - The unsigned rejection probe still runs first.
    - Status: done.

26. **Prospect tenant inheritance**
    - Prospect storage now inherits tenant ownership from the parent engagement when callers use the legacy operations service without passing a tenant ID.
    - Scoped Cal.com webhooks can book API/CSV-created contacts instead of only manually tenant-stamped prospects.
    - A regression test covers the product path from operations-created contact to scoped booking webhook.
    - Status: done.

27. **Scoped booking webhook live deploy exercise**
    - The live production smoke command can optionally create a disposable campaign/contact and send a signed scoped Cal.com booking webhook.
    - The smoke command verifies the scoped webhook marks the smoke contact as booked.
    - The smoke command best-effort cancels the disposable campaign after the probe.
    - Status: done.

28. **Production-safe mailbox OAuth redirects**
    - Mailbox connect/start now rejects non-mailbox callback paths.
    - Production mode rejects localhost HTTP redirects and foreign-host redirects.
    - Local/dev mode still permits localhost HTTP for developer OAuth testing.
    - Status: done.

29. **Render worker credential-secret wiring**
    - The Render worker now receives `AUTOREACH_CREDENTIAL_ENCRYPTION_KEY` so smart dispatch and reply polling can decrypt mailbox credentials.
    - The Render worker now receives `AUTOREACH_RUNTIME_SMART_DISPATCH=1` so worker ticks cannot fall back to console sending.
    - The Render beat process now receives the credential encryption key for mailbox maintenance hydration.
    - Status: done.

30. **Production JWT fail-closed guard**
    - Production-like deployments no longer issue JWTs with the dev fallback secret.
    - Auth signup returns a clear 503 when `AUTOREACH_JWT_SECRET` is missing or set to the known dev value in production mode.
    - Local SQLite/dev flows still keep the developer fallback.
    - Status: done.

31. **Executable live-ops launch kit**
    - Operators can generate production-grade JWT/session/Fernet/Cal.com secrets from one command.
    - Operators can generate a deploy-specific launch plan that checks required Render envs, derives Google OAuth and Cal.com URLs, emits DNS and smoke-test commands, and redacts configured secrets.
    - A live-ops runbook now covers deploy, secrets, DNS, OAuth, Cal.com metadata, Phoenix, warmed mailboxes, and pilot onboarding.
    - Status: done.
