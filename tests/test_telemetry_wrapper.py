import json
from unittest.mock import AsyncMock, patch

import pytest

from engine.runtime.context import ExecutionResult, TenantContext
from engine.telemetry.tracer import TracedWorkerContext


@pytest.fixture
def mock_base_worker():
    worker = AsyncMock()
    worker.execute_task.return_value = ExecutionResult(
        success=True,
        output={"crm_status": "updated"},
        duration_ms=45.0,
    )
    return worker


@pytest.mark.asyncio
async def test_telemetry_wrapper_injects_trace_id_and_attributes(mock_base_worker):
    tenant = TenantContext(
        tenant_id="t-99",
        campaign_id="cmp-11",
        variables={},
        encrypted_secrets={},
    )
    traced_worker = TracedWorkerContext(base_executor=mock_base_worker)

    with patch("engine.telemetry.tracer.tracer.start_as_current_span") as mock_start_span:
        mock_span = mock_start_span.return_value.__enter__.return_value
        mock_span.get_span_context.return_value.trace_id = 0xABCDEF123456

        result = await traced_worker.execute_task("update_crm", {"lead_id": "123"}, tenant)

        mock_base_worker.execute_task.assert_called_once()
        assert result.trace_id == format(0xABCDEF123456, "032x")
        mock_span.set_attribute.assert_any_call("openinference.span.kind", "AGENT")
        mock_span.set_attribute.assert_any_call("input.value", json.dumps({"lead_id": "123"}))
        mock_span.set_attribute.assert_any_call(
            "output.value",
            json.dumps({"crm_status": "updated"}),
        )
        mock_span.set_attribute.assert_any_call("tenant.id", "t-99")
