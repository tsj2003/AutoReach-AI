"""MCP-backed worker execution context."""

from __future__ import annotations

import time
from typing import Any, Optional

from engine.integrations.mcp_gateway import MCPGatewayClient
from engine.runtime.context import ExecutionResult, TenantContext, WorkerExecutionContext


class MCPWorkerContext(WorkerExecutionContext):
    """Worker driver that proxies external tool calls through MCP."""

    def __init__(self, *, gateway: Optional[MCPGatewayClient] = None) -> None:
        self._gateway = gateway

    async def execute_task(
        self,
        *,
        task_name: str,
        payload: dict[str, Any],
        context: TenantContext,
    ) -> ExecutionResult:
        started = time.perf_counter()
        try:
            if task_name != "mcp_proxy":
                raise ValueError(f"unsupported MCP task: {task_name}")
            tool_name = payload["tool_name"]
            arguments = dict(payload.get("arguments") or {})
            result = await self._gateway_for(context).execute_tool(
                tool_name,
                arguments=arguments,
            )
            return ExecutionResult(
                success=True,
                output=result,
                duration_ms=self._elapsed_ms(started),
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                duration_ms=self._elapsed_ms(started),
                error=str(exc),
            )

    def _gateway_for(self, context: TenantContext) -> MCPGatewayClient:
        if self._gateway is not None:
            return self._gateway
        return MCPGatewayClient(server_url=context.variables.get("mcp_server_url"))

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return max((time.perf_counter() - started) * 1000.0, 0.001)
