"""CRM source-of-truth sync via tenant MCP tools with real integration."""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any

from engine.runtime.context import TenantContext
from engine.integrations.mcp_gateway import crm_sync_service

logger = logging.getLogger(__name__)


class CRMSyncAgent:
    """Sync campaign outcomes to a tenant CRM through MCP with real integration."""

    def __init__(self) -> None:
        self._crm_service = crm_sync_service

    async def sync_outcome(
        self,
        tenant_context: TenantContext,
        prospect_email: str,
        outcome_type: str,
        notes: str,
    ) -> bool:
        """Sync an outcome to the tenant's CRM via MCP."""
        if not self._has_mcp_config(tenant_context):
            logger.warning(f"No MCP configuration for tenant {tenant_context.tenant_id}")
            return False

        try:
            config = self._extract_mcp_config(tenant_context)
            success = await self._crm_service.sync_outcome(
                tenant_id=tenant_context.tenant_id,
                config=config,
                prospect_email=prospect_email,
                outcome_type=outcome_type,
                notes=notes
            )
            
            if success:
                logger.info(f"Successfully synced outcome to CRM for {prospect_email}")
            else:
                logger.warning(f"Failed to sync outcome to CRM for {prospect_email}")
            
            return success
        except Exception as e:
            logger.error(f"CRM sync error for {prospect_email}: {e}")
            return False

    async def enrich_from_crm(
        self,
        tenant_context: TenantContext,
        prospect_email: str,
    ) -> Optional[Dict[str, Any]]:
        """Enrich prospect data from CRM."""
        if not self._has_mcp_config(tenant_context):
            return None

        try:
            config = self._extract_mcp_config(tenant_context)
            contact_info = await self._crm_service.get_contact_info(
                tenant_id=tenant_context.tenant_id,
                config=config,
                email=prospect_email
            )
            
            if contact_info:
                logger.info(f"Enriched prospect {prospect_email} from CRM")
            return contact_info
        except Exception as e:
            logger.error(f"CRM enrichment error for {prospect_email}: {e}")
            return None

    @staticmethod
    def _has_mcp_config(tenant_context: TenantContext) -> bool:
        """Check if tenant has MCP configuration."""
        return bool(
            tenant_context.variables.get("mcp_server_url")
            or tenant_context.variables.get("mcp_server_command")
        )

    @staticmethod
    def _extract_mcp_config(tenant_context: TenantContext) -> Dict[str, Any]:
        """Extract MCP configuration from tenant context."""
        return {
            "server_url": tenant_context.variables.get("mcp_server_url"),
            "server_command": tenant_context.variables.get("mcp_server_command"),
        }
