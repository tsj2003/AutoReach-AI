# Phase 6 Evidence Log

Last updated: 2026-09-02 (local audit)

| Feature | Implemented? | Tested? | Live Verified? | Evidence | Environment | External Dep | Limitation | Market Claim? |
|---------|-------------|---------|----------------|----------|-------------|--------------|------------|---------------|
| Webhook HMAC | YES | YES | YES (local) | `tests/test_webhook_replay.py` | sqlite TestClient | none | — | YES — signed webhooks |
| Webhook replay protection | YES | YES | YES (local) | timestamp + idempotency + DB replay store | sqlite | none | 300s default window | YES — replay-safe idempotency |
| RSS polling | YES | YES | YES | TechCrunch live fetch in audit | network | public feed | 15min beat, not real-time | YES — polling only |
| Signal persistence | YES | YES | YES (local) | signal tests | sqlite | — | — | YES |
| Enrichment profile+DNS | YES | YES | YES (local) | phase5 tests | — | DNS | MX ≠ verified inbox | YES with caveats |
| Paid enrichment | NO | N/A | NO | NotConfigured stubs | — | API keys | — | NO |
| MCP server (stdio) | YES | YES | PARTIAL | 5 tools registered; auth module | local | JWT | single-tenant per process | YES — stdio only |
| MCP ClientSession | YES | PARTIAL | PARTIAL | `tests/test_mcp_handshake.py` (integration, stdio subprocess) | local | JWT | run with `-m integration` | PARTIAL |
| Gmail send idempotency | YES | YES | YES (local) | `tests/test_reply_send_idempotency.py` | sqlite | — | deterministic job id | YES — no double-send on retry |
| Gmail proof script | YES | PARTIAL | NO | `scripts/gmail_proof_chain.py` | local | OAuth mailbox | dry-run without tenant | NO |
| Gmail receive | YES | YES | NO | unit tests only | — | OAuth | — | NO |
| Learning weekly | YES | YES | YES (local) | returns insufficient | — | event history | reporting only | YES — measurement not learning |
| CampaignLearningEngine | YES | NO | NO | unwired in-memory | — | — | prototype | NO |
| Production deploy | NO | NO | NO | DNS unresolved 2026-09-03 | DO | DNS/secrets | NO |
| Campaign/mailbox pause APIs | YES | YES | NO | `tests/test_pilot_kill_switches.py` | local | — | YES — operator kill switches |
| Engine paused flag | YES | YES | NO | `AUTOREACH_ENGINE_PAUSED` | worker/beat | — | YES |
