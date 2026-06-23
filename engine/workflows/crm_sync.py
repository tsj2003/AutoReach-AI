"""CRM source-of-truth sync via tenant MCP tools."""

from __future__ import annotations

from engine.runtime.context import TenantContext
from engine.runtime.mcp_worker import MCPWorkerContext


class CRMSyncAgent:
    """Sync campaign outcomes to a tenant CRM through MCP."""

    def __init__(self, *, mcp_worker: MCPWorkerContext) -> None:
        self.mcp_worker = mcp_worker

    async def sync_outcome(
        self,
        tenant_context: TenantContext,
        prospect_email: str,
        outcome_type: str,
        notes: str,
    ) -> bool:
        if not self._has_mcp_config(tenant_context):
            return False

        result = await self.mcp_worker.execute_task(
            task_name="mcp_proxy",
            payload={
                "tool_name": "log_crm_activity",
                "arguments": {
                    "email": prospect_email,
                    "outcome": outcome_type,
                    "notes": notes,
                },
            },
            context=tenant_context,
        )
        return bool(result.success)

    @staticmethod
    def _has_mcp_config(tenant_context: TenantContext) -> bool:
        return bool(
            tenant_context.variables.get("mcp_server_url")
            or tenant_context.variables.get("mcp_server_command")
        )
