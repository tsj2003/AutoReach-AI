import pytest
from engine.workflows.crm_sync import CRMSyncAgent
from engine.core.types import TenantContext


@pytest.mark.asyncio
async def test_crm_sync_agent_logs_activity_via_mcp():
    ctx = TenantContext(
        tenant_id="t-crm-1",
        campaign_id="cmp-1",
        variables={"mcp_server_url": "http://localhost:3000"},
        encrypted_secrets={},
    )
    agent = CRMSyncAgent()
    result = await agent.sync_outcome(
        tenant_context=ctx,
        prospect_email="ceo@target.com",
        outcome_type="MEETING_BOOKED",
        notes="Meeting set for Tuesday 2pm.",
    )
    # No real MCP server — must fail closed, not simulate success
    assert result is False


@pytest.mark.asyncio
async def test_crm_sync_agent_skips_if_no_mcp_configured():
    ctx_no_crm = TenantContext(
        tenant_id="t-crm-2",
        campaign_id="cmp-2",
        variables={},
        encrypted_secrets={},
    )
    agent = CRMSyncAgent()
    result = await agent.sync_outcome(ctx_no_crm, "dev@test.com", "EMAIL_SENT", "")
    assert result is False


@pytest.mark.asyncio
async def test_crm_enrichment():
    ctx = TenantContext(
        tenant_id="t-crm-3",
        campaign_id="cmp-3",
        variables={"mcp_server_url": "http://localhost:3000"},
        encrypted_secrets={},
    )
    agent = CRMSyncAgent()
    enriched = await agent.enrich_from_crm(ctx, "enrich@test.com")
    assert enriched is None
