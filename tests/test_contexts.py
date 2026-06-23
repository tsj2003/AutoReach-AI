import pytest
from pydantic import ValidationError

from engine.runtime.context import ExecutionResult, LocalWorkerContext, TenantContext


def test_tenant_context_strict_schema():
    """Tenant execution context requires all isolation fields."""
    with pytest.raises(ValidationError):
        TenantContext(tenant_id="t-123")

    ctx = TenantContext(
        tenant_id="t-123",
        campaign_id="cmp-456",
        variables={"company": "Acme Corp"},
        encrypted_secrets={"openai_key": "sk-dummy"},
    )
    assert ctx.tenant_id == "t-123"


@pytest.mark.asyncio
async def test_local_worker_success_execution():
    """LocalWorkerContext returns a properly formatted ExecutionResult."""
    ctx = TenantContext(
        tenant_id="t-123",
        campaign_id="cmp-456",
        variables={},
        encrypted_secrets={},
    )
    worker = LocalWorkerContext()

    result = await worker.execute_task(
        task_name="dummy_task",
        payload={"action": "evaluate"},
        context=ctx,
    )

    assert isinstance(result, ExecutionResult)
    assert result.success is True
    assert result.duration_ms > 0
    assert result.error is None


@pytest.mark.asyncio
async def test_local_worker_isolation_failure():
    """Task crashes are contained inside the worker result."""
    ctx = TenantContext(
        tenant_id="t-123",
        campaign_id="cmp-456",
        variables={},
        encrypted_secrets={},
    )
    worker = LocalWorkerContext()

    result = await worker.execute_task(
        task_name="force_crash",
        payload={},
        context=ctx,
    )

    assert result.success is False
    assert result.error is not None
