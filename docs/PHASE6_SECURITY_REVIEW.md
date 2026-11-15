# Phase 6 Security Review

## Resolved this phase

| Finding | Severity | Status | Mitigation |
|---------|----------|--------|------------|
| Webhook replay (HMAC only) | HIGH | **FIXED** | Timestamp + idempotency key + persistent `signal_webhook_replays` table with UNIQUE constraint |
| HMAC on parsed JSON vs raw body | MEDIUM | **FIXED** | Documented contract; verify raw bytes only |
| MCP tenant from tool args | MEDIUM | **PARTIAL** | `engine/mcp/auth.py` — tenant from ContextVar; campaign ownership check |
| Secret in API list responses | LOW | **FIXED** | Webhook secret redacted as `***` in list API |
| Legacy console tests broken by .env | INFO | **FIXED** | `tests/conftest.py` re-enables console for legacy tests |

## Open findings

| Finding | Severity | Status | Notes |
|---------|----------|--------|-------|
| MCP per-request JWT (stdio) | MEDIUM | OPEN | Stdio binds tenant at process start; document single-tenant-per-process |
| MCP ClientSession not verified | MEDIUM | **PARTIAL** | Integration test passes locally; not production-hosted |
| Production deploy not verified | HIGH | OPEN | DNS unresolved 2026-09-03 |
| Gmail live send unverified | HIGH | OPEN | Blocked on OAuth mailbox + reachable deploy |
| Placeholder secrets in `.do/app.yaml` | HIGH | OPEN | Must be overridden in DO UI before pilot |
| Unwired enrichment/learning flags | MEDIUM | **FIXED** | APIs now 503 when flags off |
| Missing campaign/mailbox pause | MEDIUM | **FIXED** | JWT pause/resume endpoints + engine pause flag |

## Attack surfaces tested

- Cross-tenant REST (campaign, webhook source, inbox) — `tests/test_tenant_isolation_attack.py`
- Webhook invalid signature, expired timestamp, idempotency replay — `tests/test_webhook_replay.py`
- MCP auth without tenant context — `tests/test_mcp_handshake.py`
