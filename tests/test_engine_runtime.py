import pytest
from unittest.mock import AsyncMock, patch

from engine.runtime.context import ExecutionResult, TenantContext
from engine.runtime.runtime import AgentEngineRuntime


@pytest.fixture
def mock_executor():
    executor = AsyncMock()
    executor.execute_task.return_value = ExecutionResult(
        success=True,
        output={"drafted_email": "Hi there,"},
        duration_ms=45.0,
        trace_id="openinference-span-789",
    )
    return executor


@pytest.fixture
def sample_tenant():
    return TenantContext(
        tenant_id="t-abc",
        campaign_id="cmp-xyz",
        variables={},
        encrypted_secrets={},
    )


@pytest.mark.asyncio
async def test_tick_campaign_replaces_global_loop(mock_executor, sample_tenant):
    """AgentEngineRuntime delegates one explicit tenant/campaign tick."""
    engine = AgentEngineRuntime(execution_context=mock_executor)

    with patch.object(engine, "_queue_to_outbox", new_callable=AsyncMock) as mock_outbox:
        await engine.tick_campaign(tenant_context=sample_tenant, engagement_id="eng-123")

        mock_executor.execute_task.assert_called_once()
        call_kwargs = mock_executor.execute_task.call_args.kwargs
        assert call_kwargs["context"] == sample_tenant
        assert call_kwargs["payload"]["engagement_id"] == "eng-123"
        mock_outbox.assert_called_once_with(
            sample_tenant,
            {"drafted_email": "Hi there,"},
            "openinference-span-789",
        )


@pytest.mark.asyncio
async def test_tick_campaign_handles_tenant_failure(sample_tenant):
    """A failed tenant task is logged without escaping the runtime."""
    failing_executor = AsyncMock()
    failing_executor.execute_task.return_value = ExecutionResult(
        success=False,
        error="LLM Rate Limit Exceeded",
        duration_ms=1200.0,
    )

    engine = AgentEngineRuntime(execution_context=failing_executor)

    with patch.object(engine, "_log_tenant_error", new_callable=AsyncMock) as mock_log_error:
        await engine.tick_campaign(tenant_context=sample_tenant, engagement_id="eng-123")

        mock_log_error.assert_called_once_with("t-abc", "LLM Rate Limit Exceeded")
