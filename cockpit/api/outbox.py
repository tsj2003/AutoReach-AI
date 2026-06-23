"""HITL outbox approval API.

This v1 router is intentionally header-scoped so worker-generated outbox rows
can be reviewed without depending on the JWT cockpit session model.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from engine.tasks import dispatch_agent_task

PENDING_APPROVAL = "PENDING_APPROVAL"
APPROVED = "APPROVED"
REJECTED = "REJECTED"


class _ComparableField:
    """Tiny comparable field used by tests and lightweight DB adapters."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> str:  # type: ignore[override]
        return f"{self.name} == {other!r}"


class OutboxJob:
    """Minimal outbox row contract used by the HITL gateway."""

    id = _ComparableField("id")
    tenant_id = _ComparableField("tenant_id")
    status = _ComparableField("status")


db_session: Any = None

router = APIRouter(prefix="/api/v1/outbox", tags=["outbox"])


def require_tenant_id(x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID")) -> str:
    tenant_id = (x_tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required")
    return tenant_id


def _session() -> Any:
    if db_session is None:
        raise HTTPException(status_code=503, detail="Outbox database is not configured")
    return db_session


def _job_to_dict(job: Any) -> dict[str, Any]:
    return {
        "id": job.id,
        "payload": dict(getattr(job, "payload", {}) or {}),
    }


@router.get("/pending")
def pending_jobs(tenant_id: str = Depends(require_tenant_id)) -> list[dict[str, Any]]:
    session = _session()
    jobs = (
        session.query(OutboxJob)
        .filter(OutboxJob.tenant_id == tenant_id, OutboxJob.status == PENDING_APPROVAL)
        .all()
    )
    return [_job_to_dict(job) for job in jobs]


@router.post("/{job_id}/approve")
def approve_job(job_id: str, tenant_id: str = Depends(require_tenant_id)) -> dict[str, bool]:
    session = _session()
    job = (
        session.query(OutboxJob)
        .filter(OutboxJob.id == job_id, OutboxJob.tenant_id == tenant_id)
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Outbox job not found")
    if getattr(job, "tenant_id", tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if getattr(job, "status", PENDING_APPROVAL) != PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Outbox job is not pending approval")

    job.status = APPROVED
    session.commit()
    queued_payload = dict(getattr(job, "payload", {}) or {})
    queued_payload.setdefault("job_id", job_id)
    tenant_context = dict(getattr(job, "tenant_context", {}) or {})
    tenant_context.setdefault("tenant_id", tenant_id)
    tenant_context.setdefault(
        "campaign_id",
        getattr(job, "campaign_id", None) or getattr(job, "engagement_id", ""),
    )
    tenant_context.setdefault("variables", {})
    tenant_context.setdefault("encrypted_secrets", {})
    dispatch_agent_task.apply_async(
        kwargs={
            "task_name": getattr(job, "task_name", "email_send"),
            "payload": queued_payload,
            "tenant_context": tenant_context,
        },
        queue="standard-agents",
    )
    return {"ok": True}


@router.post("/{job_id}/reject")
def reject_job(job_id: str, tenant_id: str = Depends(require_tenant_id)) -> dict[str, bool]:
    session = _session()
    job = (
        session.query(OutboxJob)
        .filter(OutboxJob.id == job_id, OutboxJob.tenant_id == tenant_id)
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Outbox job not found")
    if getattr(job, "tenant_id", tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    job.status = REJECTED
    session.commit()
    return {"ok": True}
