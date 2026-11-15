from unittest.mock import AsyncMock

import pytest

from engine.evals import AgentEvalLoop, AgentEvalReport, EvaluatedWorkerContext
from engine.runtime.context import ExecutionResult, TenantContext


@pytest.fixture
def tenant():
    return TenantContext(
        tenant_id="t-eval-1",
        campaign_id="cmp-eval-1",
        variables={},
        encrypted_secrets={"api_key": "sk_live_secret"},
    )


def test_agent_eval_passes_complete_email_draft_and_preserves_trace(tenant):
    result = ExecutionResult(
        success=True,
        output={"subject": "Congrats on the round", "body": "Saw your funding news."},
        duration_ms=25.0,
        trace_id="trace-abc",
    )

    report = AgentEvalLoop().evaluate(
        tenant_context=tenant,
        task_name="draft_email_touch",
        payload={"prospect_id": "p1"},
        result=result,
    )

    assert isinstance(report, AgentEvalReport)
    assert report.passed is True
    assert report.score == 1.0
    assert report.openinference_trace_id == "trace-abc"
    assert report.failures == []


def test_agent_eval_fails_email_draft_missing_body(tenant):
    result = ExecutionResult(
        success=True,
        output={"subject": "Quick question"},
        duration_ms=25.0,
    )

    report = AgentEvalLoop().evaluate(
        tenant_context=tenant,
        task_name="draft_email_touch",
        payload={},
        result=result,
    )

    assert report.passed is False
    assert any("body" in failure for failure in report.failures)


def test_agent_eval_fails_when_output_leaks_tenant_secret(tenant):
    result = ExecutionResult(
        success=True,
        output={"subject": "Oops", "body": "debug token sk_live_secret"},
        duration_ms=25.0,
    )

    report = AgentEvalLoop().evaluate(
        tenant_context=tenant,
        task_name="draft_email_touch",
        payload={},
        result=result,
    )

    assert report.passed is False
    assert any("secret" in failure for failure in report.failures)


@pytest.mark.asyncio
async def test_evaluated_worker_blocks_failed_agent_output(tenant):
    base_worker = AsyncMock()
    base_worker.execute_task.return_value = ExecutionResult(
        success=True,
        output={"subject": "No body"},
        duration_ms=10.0,
        trace_id="trace-blocked",
    )
    worker = EvaluatedWorkerContext(base_executor=base_worker)

    result = await worker.execute_task(
        task_name="draft_email_touch",
        payload={"prospect_id": "p1"},
        context=tenant,
    )

    assert result.success is False
    assert "agent eval failed" in result.error
    assert result.output["agent_eval"]["passed"] is False
    assert result.output["agent_eval"]["openinference_trace_id"] == "trace-blocked"


@pytest.mark.asyncio
async def test_evaluated_worker_allows_valid_output(tenant):
    base_worker = AsyncMock()
    base_worker.execute_task.return_value = ExecutionResult(
        success=True,
        output={"message": "Congrats on the raise. Let's connect."},
        duration_ms=10.0,
    )
    worker = EvaluatedWorkerContext(base_executor=base_worker)

    result = await worker.execute_task(
        task_name="draft_linkedin_connection",
        payload={"prospect_id": "p1"},
        context=tenant,
    )

    assert result.success is True
    assert result.error is None
    assert result.output["agent_eval"]["passed"] is True
