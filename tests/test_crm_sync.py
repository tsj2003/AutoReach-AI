import pytest
from unittest.mock import AsyncMock
# Cursor will implement this agent
from engine.workflows.crm_sync import CRMSyncAgent
from engine.core.types import TenantContext
from engine.runtime.context import ExecutionResult


@pytest.fixture
def mock_mcp_worker():
    """Mocks the MCPWorkerContext to simulate a successful CRM tool execution."""
    worker = AsyncMock()
    worker.execute_task.return_value = ExecutionResult(
        success=True,
        output={"status": "crm_updated", "record_id": "00Q5000000abcde"},
        duration_ms=150.0
    )
    return worker


@pytest.mark.asyncio
async def test_crm_sync_agent_logs_activity_via_mcp(mock_mcp_worker):
    """
    Forces the CRM agent to dynamically map the outcome to
    an MCP tool call, maintaining complete abstraction.
    """
    ctx = TenantContext(
        tenant_id="t-crm-1",
        campaign_id="cmp-1",
        # The presence of an MCP config flags that this tenant has connected their CRM
        variables={"mcp_server_command": "python"},
        encrypted_secrets={}
    )
    agent = CRMSyncAgent(mcp_worker=mock_mcp_worker)

    # Act: The workflow coordinator tells the CRM agent to log a meeting
    result = await agent.sync_outcome(
        tenant_context=ctx,
        prospect_email="ceo@target.com",
        outcome_type="MEETING_BOOKED",
        notes="Meeting set for Tuesday 2pm."
    )

    # Assert: The MCP worker was invoked
    assert result is True
    mock_mcp_worker.execute_task.assert_called_once()

    # Assert: The payload was correctly formatted for the MCP proxy tool
    call_kwargs = mock_mcp_worker.execute_task.call_args.kwargs
    assert call_kwargs["task_name"] == "mcp_proxy"
    assert call_kwargs["payload"]["tool_name"] == "log_crm_activity"
    assert call_kwargs["payload"]["arguments"]["email"] == "ceo@target.com"
    assert call_kwargs["payload"]["arguments"]["outcome"] == "MEETING_BOOKED"


@pytest.mark.asyncio
async def test_crm_sync_agent_skips_if_no_mcp_configured(mock_mcp_worker):
    """Ensures the agent gracefully skips CRM sync if the client hasn't connected one."""
    ctx_no_crm = TenantContext(
        tenant_id="t-crm-2",
        campaign_id="cmp-2",
        variables={}, # No MCP configuration
        encrypted_secrets={}
    )
    agent = CRMSyncAgent(mcp_worker=mock_mcp_worker)

    result = await agent.sync_outcome(ctx_no_crm, "dev@test.com", "EMAIL_SENT", "")

    # Must return False (or gracefully skip) without crashing the main thread
    assert result is False
    mock_mcp_worker.execute_task.assert_not_called()
