import pytest
from engine.integrations.mcp_gateway import MCPGatewayClient


@pytest.mark.asyncio
async def test_mcp_gateway_initialization():
    gateway = MCPGatewayClient(server_url="http://localhost:3000")
    assert gateway is not None


@pytest.mark.asyncio
async def test_mcp_tool_discovery_unconfigured():
    gateway = MCPGatewayClient()
    tools = await gateway.discover_tools()
    assert tools == []


@pytest.mark.asyncio
async def test_mcp_tool_discovery_http_not_implemented():
    gateway = MCPGatewayClient(server_url="http://localhost:3000")
    tools = await gateway.discover_tools()
    assert tools == []


@pytest.mark.asyncio
async def test_mcp_tool_execution_not_connected():
    gateway = MCPGatewayClient(server_url="http://localhost:3000")
    with pytest.raises(RuntimeError, match="not connected|failed"):
        await gateway.execute_tool(
            tool_name="log_crm_activity",
            arguments={"email": "buyer@acme.com", "outcome": "meeting", "notes": "test"},
        )


@pytest.mark.asyncio
async def test_mcp_error_handling_unknown_tool():
    gateway = MCPGatewayClient()
    with pytest.raises(RuntimeError):
        await gateway.execute_tool(
            tool_name="nonexistent_tool",
            arguments={"email": "test@example.com"},
        )
