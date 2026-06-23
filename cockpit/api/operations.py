"""Internal operations API for OaaS pilot onboarding."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from cockpit.api.deps import get_current_user
from cockpit.services.launch_checklist import PilotLaunchChecklist, LaunchChecklistResult
from cockpit.services.onboarding import OnboardingService, TenantOnboardingPayload
from cockpit.services.preflight import DeliverabilityPreflight
from cockpit.services.readiness import ProductionReadiness, runtime_dependency_checks
from engine.auth import CurrentUser

router = APIRouter(prefix="/api/operations", tags=["operations"])


class PilotOnboardingRequest(BaseModel):
    company_name: str
    domain: str
    budget_limit: Decimal
    meeting_price: Decimal
    linkedin_enabled: bool = False
    mcp_server_command: Optional[str] = None
    mcp_server_url: Optional[str] = None


class CampaignPreflightRequest(BaseModel):
    domain: str


def _require_operator(current_user: CurrentUser) -> CurrentUser:
    if current_user.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owners and admins can onboard pilot tenants")
    return current_user


@router.post("/pilot-onboarding", status_code=201)
async def pilot_onboarding(
    body: PilotOnboardingRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _require_operator(current_user)
    result = await OnboardingService(db=request.app.state.store).register_tenant(
        TenantOnboardingPayload(
            company_name=body.company_name,
            domain=body.domain,
            budget_limit=body.budget_limit,
            meeting_price=body.meeting_price,
            linkedin_enabled=body.linkedin_enabled,
            mcp_server_command=body.mcp_server_command,
            mcp_server_url=body.mcp_server_url,
        )
    )
    tenant_context = (
        result.tenant_context.model_dump()
        if hasattr(result.tenant_context, "model_dump")
        else result.tenant_context.dict()
    )
    return {
        "tenant_id": result.tenant_id,
        "company_name": result.company_name,
        "domain": result.domain,
        "status": result.status,
        "is_safe_to_send": result.preflight.is_safe_to_send,
        "failure_reasons": result.preflight.failure_reasons,
        "tenant_context": tenant_context,
    }


@router.get("/campaigns/{campaign_id}/launch-checklist")
def campaign_launch_checklist(
    campaign_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _require_operator(current_user)
    result = PilotLaunchChecklist(store=request.app.state.store).evaluate(
        tenant_id=current_user.tenant_id,
        campaign_id=campaign_id,
    )
    if not any(item.key == "campaign_scope" and not item.passed for item in result.items):
        return _launch_result_to_dict(result)
    raise HTTPException(404, "Campaign not found")


@router.post("/campaigns/{campaign_id}/deliverability-preflight")
async def campaign_deliverability_preflight(
    campaign_id: str,
    body: CampaignPreflightRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _require_operator(current_user)
    store = request.app.state.store
    engagement = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if engagement is None:
        raise HTTPException(404, "Campaign not found")

    normalized_domain = body.domain.strip().lower().rstrip(".")
    if not normalized_domain:
        raise HTTPException(400, "Sending domain is required")

    result = await DeliverabilityPreflight().verify_domain(normalized_domain)
    preflight_payload = {
        "domain": normalized_domain,
        "is_safe_to_send": result.is_safe_to_send,
        "failure_reasons": list(result.failure_reasons),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata = dict(getattr(engagement, "metadata", {}) or {})
    metadata["deliverability_preflight"] = preflight_payload
    store.save_engagement(
        replace(engagement, metadata=metadata),
        tenant_id=current_user.tenant_id,
    )

    return {
        "tenant_id": current_user.tenant_id,
        "campaign_id": campaign_id,
        **preflight_payload,
    }


@router.get("/mission-control")
def mission_control(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _require_operator(current_user)
    store = request.app.state.store
    pnl = request.app.state.pnl
    tenant_id = current_user.tenant_id
    engagements = list(store.list_engagements(tenant_id=tenant_id))
    checklist = PilotLaunchChecklist(store=store)

    pending_approval_count = 0
    booked_meeting_count = 0
    budget_risk_count = 0
    blocked_launches: list[dict[str, Any]] = []

    for engagement in engagements:
        pending_approval_count += len(
            list(store.list_jobs_by_state("awaiting_approval", engagement_id=engagement.id))
        )
        booked_meeting_count += sum(
            1
            for meeting in store.list_meetings(engagement.id, limit=1000)
            if meeting.status in ("booked", "qualified")
        )
        report = pnl.report_for(engagement.id)
        if getattr(report, "over_budget", False):
            budget_risk_count += 1
        launch = checklist.evaluate(tenant_id=tenant_id, campaign_id=engagement.id)
        if not launch.is_launch_ready:
            blocked_launches.append(
                {
                    "campaign_id": engagement.id,
                    "customer_name": engagement.customer_name,
                    "failed_keys": [
                        item.key for item in launch.items if not item.passed
                    ],
                }
            )

    list_mailboxes = getattr(store, "list_mailboxes", None)
    mailboxes = list(list_mailboxes(tenant_id)) if callable(list_mailboxes) else []
    mailbox_counts: dict[str, int] = {}
    for mailbox in mailboxes:
        status = getattr(mailbox, "status", "unknown") or "unknown"
        mailbox_counts[status] = mailbox_counts.get(status, 0) + 1

    return {
        "tenant_id": tenant_id,
        "campaign_count": len(engagements),
        "blocked_launch_count": len(blocked_launches),
        "blocked_launches": blocked_launches,
        "pending_approval_count": pending_approval_count,
        "booked_meeting_count": booked_meeting_count,
        "budget_risk_count": budget_risk_count,
        "mailbox_counts": mailbox_counts,
    }


@router.get("/readiness")
def production_readiness(
    request: Request,
    deep: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _require_operator(current_user)
    import os

    extra_checks = (
        runtime_dependency_checks(store=request.app.state.store, env=os.environ)
        if deep else None
    )
    return ProductionReadiness(env=os.environ).evaluate(extra_checks=extra_checks).model_dump()


@router.get("/campaigns/{campaign_id}/proof-package")
def campaign_proof_package(
    campaign_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _require_operator(current_user)
    store = request.app.state.store
    engagement = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if engagement is None:
        raise HTTPException(404, "Campaign not found")

    report = request.app.state.pnl.report_for(campaign_id)
    meetings = list(store.list_meetings(campaign_id, limit=1000))
    events = list(request.app.state.events.list_recent(engagement_id=campaign_id, limit=100))
    trace_ids = sorted(
        {
            trace_id
            for event in events
            for trace_id in _trace_ids_from_payload(dict(event.payload))
        }
    )

    return {
        "tenant_id": current_user.tenant_id,
        "campaign": {
            "id": engagement.id,
            "customer_name": engagement.customer_name,
            "status": engagement.status,
            "offer": engagement.offer,
            "icp_description": engagement.icp_description,
        },
        "economics": {
            "revenue_cents": report.revenue_cents if report else 0,
            "cost_cents": report.cost_cents if report else 0,
            "margin_cents": report.margin_cents if report else 0,
            "qualified_count": report.qualified_count if report else 0,
            "booked_count": report.booked_count if report else 0,
            "cost_by_category_cents": report.cost_by_category_cents if report else {},
        },
        "outcomes": [
            {
                "meeting_id": meeting.id,
                "prospect_id": meeting.prospect_id,
                "status": meeting.status,
                "scheduled_for": meeting.scheduled_for.isoformat(),
                "notes": meeting.notes,
            }
            for meeting in meetings
            if meeting.status in ("booked", "qualified")
        ],
        "trace_ids": trace_ids,
        "recent_events": [
            {
                "kind": event.kind.value,
                "occurred_at": event.occurred_at.isoformat(),
                "job_id": event.job_id,
                "prospect_id": event.prospect_id,
                "payload": dict(event.payload),
            }
            for event in events[:25]
        ],
    }


@router.post("/campaigns/{campaign_id}/activate")
def activate_campaign(
    campaign_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _require_operator(current_user)
    checklist = PilotLaunchChecklist(store=request.app.state.store)
    result = checklist.activate_if_ready(
        tenant_id=current_user.tenant_id,
        campaign_id=campaign_id,
    )
    if not result.is_launch_ready:
        raise HTTPException(status_code=409, detail=_launch_result_to_dict(result))
    return _launch_result_to_dict(result)


def _launch_result_to_dict(result: LaunchChecklistResult) -> dict[str, Any]:
    return {
        "tenant_id": result.tenant_id,
        "campaign_id": result.campaign_id,
        "is_launch_ready": result.is_launch_ready,
        "items": [
            {
                "key": item.key,
                "label": item.label,
                "passed": item.passed,
                "detail": item.detail,
            }
            for item in result.items
        ],
    }


def _trace_ids_from_payload(payload: dict[str, Any]) -> list[str]:
    trace_ids: list[str] = []
    for key in ("openinference_trace_id", "trace_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            trace_ids.append(value)
    raw = payload.get("raw")
    if isinstance(raw, dict):
        trace_ids.extend(_trace_ids_from_payload(raw))
    intent_signal = payload.get("intent_signal")
    if isinstance(intent_signal, dict):
        trace_ids.extend(_trace_ids_from_payload(intent_signal))
    return trace_ids
