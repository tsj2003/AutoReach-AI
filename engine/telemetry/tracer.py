"""OpenTelemetry/OpenInference tracing decorator for worker contexts."""

from __future__ import annotations

import json
import time
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from engine.runtime.context import ExecutionResult, TenantContext, WorkerExecutionContext


class _DynamicTracer:
    """Resolve the active global tracer provider at execution time."""

    def start_as_current_span(self, *args: Any, **kwargs: Any) -> Any:
        return trace.get_tracer(__name__).start_as_current_span(*args, **kwargs)


tracer = _DynamicTracer()


class TracedWorkerContext(WorkerExecutionContext):
    """Decorator that adds a reasoning-ledger span around any worker executor."""

    def __init__(self, *, base_executor: WorkerExecutionContext) -> None:
        self._base_executor = base_executor

    async def execute_task(
        self,
        task_name: str,
        payload: dict[str, Any],
        context: TenantContext,
    ) -> ExecutionResult:
        started = time.perf_counter()
        with tracer.start_as_current_span(task_name) as span:
            span.set_attribute("openinference.span.kind", "AGENT")
            span.set_attribute("tenant.id", context.tenant_id)
            span.set_attribute("campaign.id", context.campaign_id)
            span.set_attribute("task.name", task_name)
            span.set_attribute("input.value", json.dumps(payload, default=str))

            try:
                result = await self._base_executor.execute_task(
                    task_name=task_name,
                    payload=payload,
                    context=context,
                )
                result = self._coerce_result(result)
            except Exception as exc:
                result = ExecutionResult(
                    success=False,
                    duration_ms=max((time.perf_counter() - started) * 1000.0, 0.001),
                    error=str(exc),
                )
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))

            span.set_attribute("output.value", json.dumps(result.output, default=str))
            if result.error is not None:
                span.set_attribute("error.message", result.error)
            span.set_attribute("execution.success", result.success)
            span.set_attribute("execution.duration_ms", result.duration_ms)

            trace_id = span.get_span_context().trace_id
            result.trace_id = format(trace_id, "032x")
            return result

    @staticmethod
    def _coerce_result(result: Any) -> ExecutionResult:
        if isinstance(result, ExecutionResult):
            return result
        if hasattr(ExecutionResult, "model_validate"):
            return ExecutionResult.model_validate(result)
        return ExecutionResult.parse_obj(result)  # pragma: no cover
