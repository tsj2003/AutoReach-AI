# Attainly Capability Matrix

Source of truth for marketing claims. Status values: `IMPLEMENTED` | `TESTED` | `LIVE_VERIFIED` | `NOT_CONFIGURED` | `EXPERIMENTAL` | `BLOCKED`

| Capability | Status | Evidence | Safe to market | Limitation |
|------------|--------|----------|----------------|------------|
| 18 registered signal types | TESTED | `engine/signals/registry.py` + tests | YES | Not "30+" |
| Signed webhook ingestion | LIVE_VERIFIED (local) | `tests/test_webhook_replay.py` | YES | Requires timestamp + idempotency key |
| Webhook replay protection | TESTED | `signal_webhook_replays` table | YES | Configurable TTL |
| RSS/Atom connector | LIVE_VERIFIED (fetch) | live TechCrunch + unit tests | YES | Polling, noisy classifier |
| Signal matrix fail-closed | TESTED | intent ingestor tests | YES | — |
| HITL outbound approval | TESTED | outbox API tests | YES | — |
| Profile enrichment | TESTED | waterfall tests | YES | Uses existing record data |
| DNS MX lookup | TESTED | providers tests | YES (caveat) | "Domain has MX" not "email verified" |
| Apollo/Clearbit/Hunter | NOT_CONFIGURED | NotConfiguredProvider | NO | Interface only |
| Attainly MCP stdio server | IMPLEMENTED | `engine/mcp/server.py` | PARTIAL | Single-tenant per process |
| MCP ClientSession handshake | INTEGRATION VERIFIED | `tests/test_mcp_handshake.py -m integration` | PARTIAL | Not production-hosted |
| External CRM MCP | BLOCKED | fail-closed without server | NO | — |
| Gmail send/receive | IMPLEMENTED | unit + idempotency; no live mailbox on deploy | NO | OAuth + DNS required |
| Campaign/mailbox pause | TESTED | `tests/test_pilot_kill_switches.py` | YES | Operator kill switches |
| Engine global pause | TESTED | `AUTOREACH_ENGINE_PAUSED` | YES | Worker/beat env |
| Weekly measurement API | TESTED | gated by `AUTOREACH_LEARNING_ENABLED` | YES | Off by default |
| CampaignLearningEngine | EXPERIMENTAL | unwired prototype | NO | — |
| Production deploy | BLOCKED | DNS unresolved / probe failed 2026-09-03 | NO | Must restore public URL |
| Hunter enrichment | IMPLEMENTED | `HunterProvider` + tests; live needs `HUNTER_API_KEY` | PARTIAL | Key required |
| Account entity | TESTED | `accounts` table + `/api/campaigns/{id}/accounts` | YES | Domain-keyed |
| Contactable launch gate | TESTED | launch checklist item | YES | ≥1 email required |
| Lead plan caps | TESTED | `assert_under_lead_cap` on create/upload/scrape | YES | — |
| Advisory learning recommendations | TESTED | weekly report `recommendations` (non-mutating) | YES | Flag-gated |
