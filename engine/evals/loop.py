"""Deterministic agent evaluation loop."""

from __future__ import annotations

import json
from typing import Any

from engine.evals.models import AgentEvalReport, EvalCheckResult
from engine.runtime.context import ExecutionResult, TenantContext, WorkerExecutionContext


class AgentEvalLoop:
    """Run low-latency quality and safety checks on agent outputs."""

    EMAIL_DRAFT_TASKS = {"draft_email", "draft_email_touch", "draft_reply_email"}
    LINKEDIN_DRAFT_TASKS = {"draft_linkedin_connection", "draft_linkedin_touch"}

    def __init__(self, *, min_score: float = 1.0) -> None:
        self.min_score = min_score

    def evaluate(
        self,
        *,
        tenant_context: TenantContext,
        task_name: str,
        payload: dict[str, Any],
        result: ExecutionResult,
    ) -> AgentEvalReport:
        checks = [
            self._check_execution_success(result),
            self._check_output_present(result),
            self._check_required_draft_fields(task_name, result),
            self._check_secret_leakage(tenant_context, payload, result),
        ]
        score = sum(check.score for check in checks) / len(checks)
        failures = [check.message for check in checks if not check.passed]
        passed = not failures and score >= self.min_score

        return AgentEvalReport(
            tenant_id=tenant_context.tenant_id,
            campaign_id=tenant_context.campaign_id,
            task_name=task_name,
            passed=passed,
            score=score,
            checks=checks,
            failures=failures,
            openinference_trace_id=result.trace_id,
        )

    @staticmethod
    def _pass(name: str, message: str = "passed") -> EvalCheckResult:
        return EvalCheckResult(name=name, passed=True, score=1.0, message=message)

    @staticmethod
    def _fail(name: str, message: str) -> EvalCheckResult:
        return EvalCheckResult(name=name, passed=False, score=0.0, message=message)

    def _check_execution_success(self, result: ExecutionResult) -> EvalCheckResult:
        if result.success:
            return self._pass("execution_success")
        return self._fail("execution_success", result.error or "agent execution failed")

    def _check_output_present(self, result: ExecutionResult) -> EvalCheckResult:
        if result.output not in (None, "", {}, []):
            return self._pass("output_present")
        return self._fail("output_present", "agent output is empty")

    def _check_required_draft_fields(self, task_name: str, result: ExecutionResult) -> EvalCheckResult:
        output = self._output_dict(result.output)
        draft = self._output_dict(output.get("draft", output))

        if task_name in self.EMAIL_DRAFT_TASKS:
            missing = [field for field in ("subject", "body") if not str(draft.get(field, "")).strip()]
            if missing:
                return self._fail(
                    "required_draft_fields",
                    f"email draft missing required field(s): {', '.join(missing)}",
                )

        if task_name in self.LINKEDIN_DRAFT_TASKS and not str(draft.get("message", "")).strip():
            return self._fail(
                "required_draft_fields",
                "linkedin draft missing required field: message",
            )

        return self._pass("required_draft_fields")

    def _check_secret_leakage(
        self,
        tenant_context: TenantContext,
        payload: dict[str, Any],
        result: ExecutionResult,
    ) -> EvalCheckResult:
        text = self._stringify({"payload": payload, "output": result.output})
        for key, value in tenant_context.encrypted_secrets.items():
            secret = str(value)
            if secret and len(secret) >= 6 and secret in text:
                return self._fail("secret_leakage", f"agent output leaked tenant secret: {key}")
        return self._pass("secret_leakage")

    @staticmethod
    def _output_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _stringify(value: Any) -> str:
        try:
            return json.dumps(value, default=str, sort_keys=True)
        except TypeError:
            return str(value)


class EvaluatedWorkerContext(WorkerExecutionContext):
    """Worker wrapper that attaches eval reports and can block failed outputs."""

    def __init__(
        self,
        *,
        base_executor: WorkerExecutionContext,
        evaluator: AgentEvalLoop | None = None,
        block_on_failure: bool = True,
    ) -> None:
        self._base_executor = base_executor
        self._evaluator = evaluator or AgentEvalLoop()
        self._block_on_failure = block_on_failure

    async def execute_task(
        self,
        task_name: str,
        payload: dict[str, Any],
        context: TenantContext,
    ) -> ExecutionResult:
        result = await self._base_executor.execute_task(
            task_name=task_name,
            payload=payload,
            context=context,
        )
        if not isinstance(result, ExecutionResult):
            result = ExecutionResult.model_validate(result)

        report = self._evaluator.evaluate(
            tenant_context=context,
            task_name=task_name,
            payload=payload,
            result=result,
        )
        result.output = self._attach_report(result.output, report)

        if self._block_on_failure and not report.passed:
            result.success = False
            result.error = f"agent eval failed: {'; '.join(report.failures)}"

        return result

    @staticmethod
    def _attach_report(output: Any, report: AgentEvalReport) -> dict[str, Any]:
        report_payload = report.model_dump() if hasattr(report, "model_dump") else report.dict()
        if isinstance(output, dict):
            return {**output, "agent_eval": report_payload}
        return {"value": output, "agent_eval": report_payload}
