"""Model Context Protocol gateway client.

The engine should not know whether a tenant exposes HubSpot, Salesforce, Jira,
or a private database. It only needs an MCP ClientSession-like object that can
discover tools and call them. This wrapper keeps the rest of the runtime on a
small, testable contract.
"""

from __future__ import annotations

import json
from typing import Any, Optional


class MCPGatewayClient:
    """Thin wrapper around an official MCP ``ClientSession`` instance."""

    def __init__(self, *, session: Optional[Any] = None, server_url: Optional[str] = None) -> None:
        self._session = session
        self._server_url = server_url

    async def discover_tools(self) -> list[dict[str, Any]]:
        """Return MCP tools as plain dictionaries."""
        session = self._require_session()
        response = await session.list_tools()
        tools = getattr(response, "tools", response)
        return [self._tool_to_dict(tool) for tool in tools]

    async def execute_tool(self, tool_name: str, *, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool and normalize block content into app-friendly data."""
        session = self._require_session()
        response = await session.call_tool(tool_name, arguments=arguments)
        return self._parse_content(getattr(response, "content", response))

    def _require_session(self) -> Any:
        if self._session is None:
            raise RuntimeError(
                "MCP ClientSession is not configured. Provide an official MCP "
                "ClientSession or build one from server_url before executing tools."
            )
        return self._session

    @staticmethod
    def _tool_to_dict(tool: Any) -> dict[str, Any]:
        if isinstance(tool, dict):
            return dict(tool)
        data = {
            "name": getattr(tool, "name", None),
            "description": getattr(tool, "description", None),
        }
        input_schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
        if input_schema is not None:
            data["input_schema"] = input_schema
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def _parse_content(cls, content: Any) -> Any:
        if content is None:
            return None
        if isinstance(content, str):
            return cls._parse_text(content)
        if isinstance(content, dict):
            if content.get("type") == "text" and "text" in content:
                return cls._parse_text(str(content["text"]))
            return dict(content)
        if not isinstance(content, list):
            text = getattr(content, "text", None)
            if text is not None:
                return cls._parse_text(str(text))
            return content

        parsed_blocks = [cls._parse_block(block) for block in content]
        if len(parsed_blocks) == 1:
            return parsed_blocks[0]
        return parsed_blocks

    @classmethod
    def _parse_block(cls, block: Any) -> Any:
        if isinstance(block, dict):
            if block.get("type") == "text" and "text" in block:
                return cls._parse_text(str(block["text"]))
            return dict(block)
        text = getattr(block, "text", None)
        if text is not None:
            return cls._parse_text(str(text))
        return block

    @staticmethod
    def _parse_text(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
