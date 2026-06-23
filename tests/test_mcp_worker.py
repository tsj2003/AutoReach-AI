import pytest
from unittest.mock import patch

from engine.runtime.context import ExecutionResult, TenantContext
from engine.runtime.mcp_worker import MCPWorkerContext


@pytest.fixture
def sample_tenant():
    return TenantContext(
        tenant_id="t-mcp-99",
        campaign_id="cmp-mcp-11",
        variables={"mcp_server_url": "http://client-internal.local/mcp"},
        encrypted_secrets={},
    )


@pytest.mark.asyncio
@patch("engine.integrations.mcp_gateway.MCPGatewayClient.execute_tool")
async def test_worker_routes_through_mcp(mock_execute_tool, sample_tenant):
    mock_execute_tool.return_value = '{"status": "highly_qualified"}'

    worker = MCPWorkerContext()

    result = await worker.execute_task(
        task_name="mcp_proxy",
        payload={
            "tool_name": "get_hubspot_contact",
            "arguments": {"email": "ceo@startup.com"},
        },
        context=sample_tenant,
    )

    assert isinstance(result, ExecutionResult)
    assert result.success is True
    assert result.output == '{"status": "highly_qualified"}'
    mock_execute_tool.assert_called_once_with(
        "get_hubspot_contact",
        arguments={"email": "ceo@startup.com"},
    )
