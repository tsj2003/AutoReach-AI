"""Tests for MCP integration — honest fail-closed behavior without a live server."""

import pytest

from engine.integrations.mcp_client import RealMCPClient, MCPManager, mcp_manager
from engine.integrations.mcp_gateway import MCPGatewayClient, CRMSyncService, crm_sync_service
from engine.workflows.crm_sync import CRMSyncAgent
from engine.runtime.context import TenantContext


@pytest.mark.asyncio
async def test_mcp_client_initialization():
    client = RealMCPClient(server_url="http://localhost:3000")
    assert client._server_url == "http://localhost:3000"


@pytest.mark.asyncio
async def test_mcp_client_connect_http_not_implemented():
    client = RealMCPClient(server_url="http://localhost:3000")
    connected = await client.connect()
    assert connected is False


@pytest.mark.asyncio
async def test_mcp_discover_tools_without_server():
    client = RealMCPClient(server_url="http://localhost:3000")
    tools = await client.discover_tools()
    assert tools == []


@pytest.mark.asyncio
async def test_mcp_execute_tool_not_connected():
    client = RealMCPClient(server_url="http://localhost:3000")
    result = await client.execute_tool(
        "log_crm_activity",
        {"email": "test@example.com", "outcome": "meeting_booked", "notes": "Test sync"},
    )
    assert result.success is False


@pytest.mark.asyncio
async def test_mcp_gateway_compatibility():
    gateway = MCPGatewayClient()
    tools = await gateway.discover_tools()
    assert isinstance(tools, list)


@pytest.mark.asyncio
async def test_mcp_manager():
    manager = MCPManager()
    config1 = {"server_url": "http://localhost:3000"}
    config2 = {"server_url": "http://localhost:3001"}
    client1 = manager.get_client("tenant1", config1)
    client2 = manager.get_client("tenant2", config2)
    assert client1 is not client2
    assert manager.get_client("tenant1", config1) is client1


@pytest.mark.asyncio
async def test_crm_sync_service_without_server():
    service = CRMSyncService()
    success = await service.sync_outcome(
        tenant_id="test_tenant",
        config={"server_url": "http://localhost:3000"},
        prospect_email="test@example.com",
        outcome_type="meeting_booked",
        notes="Test meeting",
    )
    assert success is False


@pytest.mark.asyncio
async def test_crm_contact_lookup_without_server():
    service = CRMSyncService()
    contact = await service.get_contact_info(
        tenant_id="test_tenant",
        config={"server_url": "http://localhost:3000"},
        email="test@example.com",
    )
    assert contact is None


@pytest.mark.asyncio
async def test_crm_sync_agent_without_server():
    agent = CRMSyncAgent()
    tenant_context = TenantContext(
        tenant_id="test_tenant",
        campaign_id="test_campaign",
        variables={"mcp_server_url": "http://localhost:3000"},
        encrypted_secrets={},
    )
    success = await agent.sync_outcome(
        tenant_context=tenant_context,
        prospect_email="test@example.com",
        outcome_type="meeting_booked",
        notes="Test sync via agent",
    )
    assert success is False


@pytest.mark.asyncio
async def test_crm_enrichment_without_server():
    agent = CRMSyncAgent()
    tenant_context = TenantContext(
        tenant_id="test_tenant",
        campaign_id="test_campaign",
        variables={"mcp_server_url": "http://localhost:3000"},
        encrypted_secrets={},
    )
    enriched = await agent.enrich_from_crm(
        tenant_context=tenant_context,
        prospect_email="test@example.com",
    )
    assert enriched is None


def test_global_instances():
    assert mcp_manager is not None
    assert crm_sync_service is not None
    assert isinstance(mcp_manager, MCPManager)
    assert isinstance(crm_sync_service, CRMSyncService)
