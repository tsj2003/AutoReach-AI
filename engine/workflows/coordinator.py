"""A2A coordination for omnichannel prospect workflows."""

from __future__ import annotations

from typing import Any

from engine.runtime.context import TenantContext
from engine.tasks import dispatch_agent_task


class OmnichannelCoordinator:
    """Manager agent that fans a prospect workflow out to channel agents."""

    async def plan_and_dispatch(
        self,
        tenant_context: TenantContext,
        prospect_id: str,
        signal_data: dict[str, Any],
    ) -> None:
        payload = {
            "prospect_id": prospect_id,
            "signal_data": dict(signal_data),
        }
        tenant_payload = self._dump_context(tenant_context)

        self._dispatch("draft_email_touch", payload, tenant_payload)
        if tenant_context.variables.get("linkedin_enabled"):
            self._dispatch("draft_linkedin_connection", payload, tenant_payload)

    @staticmethod
    def _dispatch(task_name: str, payload: dict[str, Any], tenant_payload: dict[str, Any]) -> None:
        dispatch_agent_task.apply_async(
            args=[task_name, payload, tenant_payload],
            queue="standard-agents",
        )

    @staticmethod
    def _dump_context(tenant_context: TenantContext) -> dict[str, Any]:
        if hasattr(tenant_context, "model_dump"):
            return tenant_context.model_dump()
        return tenant_context.dict()  # pragma: no cover - pydantic v1 fallback
