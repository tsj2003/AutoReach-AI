"""Tenant-scoped execution contexts for the agent runtime.

This module is the boundary between the API/runtime and the worker layer. It
keeps tenant identity, secrets, queue routing, and execution results explicit
so future workers can move from local execution to Celery or sandboxes without
changing the higher-level runtime contract.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field

try:  # Pydantic v2
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - only relevant for old environments
    ConfigDict = None  # type: ignore[assignment]


class _StrictModel(BaseModel):
    """Base model that rejects unknown fields where supported."""

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid", strict=True)
    else:  # pragma: no cover
        class Config:
            extra = "forbid"


class TenantContext(_StrictModel):
    """Execution identity and per-tenant data passed into every agent task."""

    tenant_id: str
    campaign_id: str
    variables: dict[str, Any]
    encrypted_secrets: dict[str, Any]


class ExecutionResult(_StrictModel):
    """Normalized result returned by local, Celery, or sandbox execution."""

    success: bool
    output: Any = Field(default_factory=dict)
    duration_ms: float = 0.0
    trace_id: Optional[str] = None
    error: Optional[str] = None


class WorkerExecutionContext(ABC):
    """Abstract worker boundary used by the agent engine runtime."""

    @abstractmethod
    async def execute_task(
        self,
        *,
        task_name: str,
        payload: dict[str, Any],
        context: TenantContext,
    ) -> ExecutionResult:
        """Execute a tenant-scoped task and return a normalized result."""


class LocalWorkerContext(WorkerExecutionContext):
    """In-process executor for tests and local development."""

    async def execute_task(
        self,
        *,
        task_name: str,
        payload: dict[str, Any],
        context: TenantContext,
    ) -> ExecutionResult:
        started = time.perf_counter()
        try:
            await asyncio.sleep(0)
            if task_name == "force_crash":
                raise RuntimeError("forced worker crash")
            return ExecutionResult(
                success=True,
                output={"task_name": task_name, "payload": dict(payload)},
                duration_ms=self._elapsed_ms(started),
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                duration_ms=self._elapsed_ms(started),
                error=str(exc),
            )

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return max((time.perf_counter() - started) * 1000.0, 0.001)


class CeleryWorkerContext(WorkerExecutionContext):
    """Celery-backed executor with tenant-isolated queue routing."""

    CUSTOM_TASK_PREFIXES = ("custom_", "untrusted_", "sandbox_")
    CUSTOM_TASK_NAMES = {"custom_script_eval"}

    async def execute_task(
        self,
        *,
        task_name: str,
        payload: dict[str, Any],
        context: TenantContext,
    ) -> ExecutionResult:
        from engine.tasks import dispatch_agent_task

        queue = self._queue_for(task_name=task_name, context=context)
        async_result = dispatch_agent_task.apply_async(
            kwargs={
                "task_name": task_name,
                "payload": dict(payload),
                "tenant_context": self._dump_context(context),
            },
            queue=queue,
        )
        raw_result = await self._await_celery_result(async_result)
        return self._coerce_result(raw_result)

    def _queue_for(self, *, task_name: str, context: TenantContext) -> str:
        if task_name in self.CUSTOM_TASK_NAMES or task_name.startswith(self.CUSTOM_TASK_PREFIXES):
            return f"tenant-queue-{context.tenant_id}"
        return "standard-agents"

    async def _await_celery_result(self, async_result: Any) -> dict[str, Any]:
        return await asyncio.to_thread(async_result.get, timeout=300)

    @staticmethod
    def _dump_context(context: TenantContext) -> dict[str, Any]:
        if hasattr(context, "model_dump"):
            return context.model_dump()
        return context.dict()  # pragma: no cover - pydantic v1 fallback

    @staticmethod
    def _coerce_result(raw_result: Any) -> ExecutionResult:
        if isinstance(raw_result, ExecutionResult):
            return raw_result
        if hasattr(ExecutionResult, "model_validate"):
            return ExecutionResult.model_validate(raw_result)
        return ExecutionResult.parse_obj(raw_result)  # pragma: no cover
