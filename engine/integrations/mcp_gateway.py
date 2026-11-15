"""Model Context Protocol gateway client with real integration.

The engine can now connect to real MCP servers for CRM sync, replacing
the previous contract-only implementation with functional integration.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Dict

from engine.integrations.mcp_client import RealMCPClient, mcp_manager

logger = logging.getLogger(__name__)


class MCPGatewayClient:
    """Thin wrapper around the real MCP client that maintains backward compatibility."""

    def __init__(self, *, session: Optional[Any] = None, server_url: Optional[str] = None, 
                 server_command: Optional[str] = None, tenant_id: Optional[str] = None) -> None:
        self._real_client = RealMCPClient(
            server_command=server_command,
            server_url=server_url
        )
        self._tenant_id = tenant_id
        self._session = session  # Kept for backward compatibility

    async def discover_tools(self) -> list[dict[str, Any]]:
        """Return MCP tools as plain dictionaries."""
        tools = await self._real_client.discover_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema
            }
            for tool in tools
        ]

    async def execute_tool(self, tool_name: str, *, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool and normalize block content into app-friendly data."""
        result = await self._real_client.execute_tool(tool_name, arguments)
        if result.success:
            return result.data
        else:
            raise RuntimeError(f"MCP tool execution failed: {result.error}")

    async def close(self) -> None:
        """Close the MCP connection."""
        await self._real_client.close()


class CRMSyncService:
    """High-level service for CRM sync operations using MCP."""
    
    def __init__(self):
        self._manager = mcp_manager
    
    async def sync_outcome(
        self,
        tenant_id: str,
        config: Dict[str, Any],
        prospect_email: str,
        outcome_type: str,
        notes: str
    ) -> bool:
        """Sync campaign outcomes to tenant CRM through MCP."""
        return await self._manager.sync_to_crm(
            tenant_id=tenant_id,
            config=config,
            prospect_email=prospect_email,
            outcome_type=outcome_type,
            notes=notes
        )
    
    async def get_contact_info(
        self,
        tenant_id: str,
        config: Dict[str, Any],
        email: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve contact information from CRM."""
        return await self._manager.get_crm_contact(
            tenant_id=tenant_id,
            config=config,
            email=email
        )


# Global CRM sync service instance
crm_sync_service = CRMSyncService()
