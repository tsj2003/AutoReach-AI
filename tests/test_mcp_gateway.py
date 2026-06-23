import pytest
from unittest.mock import AsyncMock, MagicMock

from engine.integrations.mcp_gateway import MCPGatewayClient


@pytest.fixture
def mock_mcp_session():
    session = AsyncMock()

    mock_tools = MagicMock()
    tool1 = MagicMock()
    tool1.name = "get_hubspot_contact"
    tool1.description = "Fetch contact by email"
    mock_tools.tools = [tool1]
    session.list_tools.return_value = mock_tools

    mock_result = MagicMock()
    mock_result.content = [
        {"type": "text", "text": '{"email": "buyer@acme.com", "intent_score": 95}'}
    ]
    session.call_tool.return_value = mock_result

    return session


@pytest.mark.asyncio
async def test_mcp_tool_discovery(mock_mcp_session):
    gateway = MCPGatewayClient(session=mock_mcp_session)

    tools = await gateway.discover_tools()

    mock_mcp_session.list_tools.assert_called_once()
    assert len(tools) == 1
    assert tools[0]["name"] == "get_hubspot_contact"


@pytest.mark.asyncio
async def test_mcp_tool_execution(mock_mcp_session):
    gateway = MCPGatewayClient(session=mock_mcp_session)

    result = await gateway.execute_tool(
        tool_name="get_hubspot_contact",
        arguments={"email": "buyer@acme.com"},
    )

    mock_mcp_session.call_tool.assert_called_once_with(
        "get_hubspot_contact",
        arguments={"email": "buyer@acme.com"},
    )
    assert "intent_score" in result
