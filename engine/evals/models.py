"""Strict schemas for agent evaluation reports."""

from __future__ import annotations

from pydantic import BaseModel, Field

try:  # Pydantic v2
    from pydantic import ConfigDict, StrictStr
except ImportError:  # pragma: no cover - pydantic v1 fallback
    ConfigDict = None  # type: ignore[assignment]
    StrictStr = str  # type: ignore[assignment,misc]


class _EvalModel(BaseModel):
    """Base model that rejects unknown fields where supported."""

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid", strict=True)
    else:  # pragma: no cover
        class Config:
            extra = "forbid"


class EvalCheckResult(_EvalModel):
    """Outcome of one deterministic agent-eval check."""

    name: StrictStr
    passed: bool
    score: float
    message: StrictStr


class AgentEvalReport(_EvalModel):
    """Aggregated evaluation for one agent task execution."""

    tenant_id: StrictStr
    campaign_id: StrictStr
    task_name: StrictStr
    passed: bool
    score: float
    checks: list[EvalCheckResult] = Field(default_factory=list)
    failures: list[StrictStr] = Field(default_factory=list)
    openinference_trace_id: StrictStr | None = None
