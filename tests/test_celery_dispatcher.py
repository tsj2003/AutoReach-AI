import pytest
from unittest.mock import AsyncMock, patch

from engine.runtime.context import CeleryWorkerContext, TenantContext


@pytest.fixture
def base_context():
    return TenantContext(
        tenant_id="t-999",
        campaign_id="cmp-111",
        variables={},
        encrypted_secrets={},
    )


@pytest.mark.asyncio
@patch("engine.runtime.context.CeleryWorkerContext._await_celery_result")
@patch("engine.tasks.dispatch_agent_task.apply_async")
async def test_celery_worker_routes_to_isolated_queue(mock_apply_async, mock_await, base_context):
    """Custom high-risk scripts route to tenant-specific queues."""
    mock_await.return_value = {
        "success": True,
        "output": {"status": "done"},
        "duration_ms": 150.0,
        "trace_id": "trace-abc",
        "error": None,
    }

    worker = CeleryWorkerContext()
    await worker.execute_task(
        task_name="custom_script_eval",
        payload={"code": "print('hello')"},
        context=base_context,
    )

    mock_apply_async.assert_called_once()
    call_kwargs = mock_apply_async.call_args.kwargs
    assert call_kwargs["queue"] == "tenant-queue-t-999"


@pytest.mark.asyncio
@patch("engine.runtime.context.CeleryWorkerContext._await_celery_result")
@patch("engine.tasks.dispatch_agent_task.apply_async")
async def test_celery_worker_standard_queue(mock_apply_async, mock_await, base_context):
    """Trusted tasks route to the standard worker pool."""
    mock_await.return_value = {"success": True, "duration_ms": 10.0, "error": None}

    worker = CeleryWorkerContext()
    await worker.execute_task(
        task_name="standard_intent_check",
        payload={},
        context=base_context,
    )

    call_kwargs = mock_apply_async.call_args.kwargs
    assert call_kwargs["queue"] == "standard-agents"
