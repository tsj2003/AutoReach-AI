"""MCP client — connects to real MCP servers when configured; fails honestly otherwise."""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class MCPToolResult:
    success: bool
    data: Any
    error: Optional[str] = None


class RealMCPClient:
    """Connect to an external MCP server via stdio when server_command is set."""

    def __init__(
        self,
        *,
        server_command: Optional[str] = None,
        server_url: Optional[str] = None,
        timeout: int = 30,
    ):
        self._server_command = (server_command or "").strip() or None
        self._server_url = (server_url or "").strip() or None
        self._timeout = timeout
        self._session: Any = None
        self._exit_stack: AsyncExitStack | None = None
        self._available_tools: Dict[str, MCPTool] = {}
        self._connected = False

    def is_configured(self) -> bool:
        return bool(self._server_command or self._server_url)

    async def connect(self) -> bool:
        if self._connected:
            return True
        if not self.is_configured():
            logger.warning("MCP client not configured (set server_command or server_url)")
            return False
        if self._server_url and not self._server_command:
            logger.warning(
                "HTTP MCP transport is not implemented — use server_command (stdio) instead"
            )
            return False
        try:
            from mcp import ClientSession
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except ImportError:
            logger.error("mcp package not installed — pip install 'mcp>=1.0,<2'")
            return False

        parts = shlex.split(self._server_command or "")
        if not parts:
            return False
        command, args = parts[0], parts[1:]
        params = StdioServerParameters(
            command=command,
            args=args,
            env={**os.environ},
        )

        self._exit_stack = AsyncExitStack()
        read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(self._session.initialize(), timeout=self._timeout)
        self._connected = True
        logger.info("MCP stdio connection established")
        return True

    async def discover_tools(self) -> List[MCPTool]:
        if not self._connected:
            if not await self.connect():
                return []
        try:
            response = await asyncio.wait_for(
                self._session.list_tools(), timeout=self._timeout,
            )
            tools = [
                MCPTool(
                    name=t.name,
                    description=t.description or "",
                    input_schema=dict(t.inputSchema) if t.inputSchema else {},
                )
                for t in response.tools
            ]
            self._available_tools = {tool.name: tool for tool in tools}
            return tools
        except Exception as exc:
            logger.error("MCP tool discovery failed: %s", exc)
            return []

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        if not self._connected:
            if not await self.connect():
                return MCPToolResult(
                    success=False,
                    data=None,
                    error="MCP server not connected — configure server_command and ensure server is running",
                )
        if tool_name not in self._available_tools:
            await self.discover_tools()
        if tool_name not in self._available_tools:
            return MCPToolResult(
                success=False,
                data=None,
                error=f"Tool {tool_name} not available on MCP server",
            )
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments),
                timeout=self._timeout,
            )
            content = []
            for block in result.content or []:
                if hasattr(block, "text"):
                    content.append(block.text)
                else:
                    content.append(str(block))
            return MCPToolResult(success=True, data={"content": content})
        except Exception as exc:
            logger.error("MCP tool execution failed tool=%s: %s", tool_name, exc)
            return MCPToolResult(success=False, data=None, error=str(exc))

    async def close(self) -> None:
        if self._exit_stack:
            await self._exit_stack.aclose()
        self._exit_stack = None
        self._session = None
        self._connected = False
        self._available_tools = {}
        logger.info("MCP connection closed")


class MCPManager:
    def __init__(self) -> None:
        self._clients: Dict[str, RealMCPClient] = {}

    def get_client(self, tenant_id: str, config: Dict[str, Any]) -> RealMCPClient:
        if tenant_id not in self._clients:
            self._clients[tenant_id] = RealMCPClient(
                server_command=config.get("server_command"),
                server_url=config.get("server_url"),
            )
        return self._clients[tenant_id]

    async def sync_to_crm(
        self,
        tenant_id: str,
        config: Dict[str, Any],
        prospect_email: str,
        outcome_type: str,
        notes: str,
    ) -> bool:
        client = self.get_client(tenant_id, config)
        if not client.is_configured():
            return False
        if not await client.connect():
            return False
        result = await client.execute_tool(
            "log_crm_activity",
            {"email": prospect_email, "outcome": outcome_type, "notes": notes},
        )
        return result.success

    async def get_crm_contact(
        self,
        tenant_id: str,
        config: Dict[str, Any],
        email: str,
    ) -> Optional[Dict[str, Any]]:
        client = self.get_client(tenant_id, config)
        if not client.is_configured():
            return None
        if not await client.connect():
            return None
        result = await client.execute_tool("get_contact_info", {"email": email})
        if result.success:
            return result.data
        return None


mcp_manager = MCPManager()
