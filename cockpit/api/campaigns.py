"""
REST API: Campaigns (≡ Engagements)

GET    /api/campaigns
POST   /api/campaigns
GET    /api/campaigns/{id}
PATCH  /api/campaigns/{id}
DELETE /api/campaigns/{id}
POST   /api/campaigns/{id}/tick
POST   /api/campaigns/{id}/drain
POST   /api/campaigns/{id}/poll-replies
POST   /api/campaigns/{id}/approve-job/{job_id}
POST   /api/campaigns/{id}/reject-job/{job_id}
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cockpit.api.deps import (
    get_current_user, get_events, get_ledger, get_ops,
    get_pnl, get_reply_detector, get_runtime, get_store,
)
from engine.auth import CurrentUser

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class CampaignCreate(BaseModel):
    customer_name: str
    offer: str
    icp_description: str
    client_cure: Optional[str] = None
    allowed_signal_types: list[str] = []
    booking_url: Optional[str] = None
    monthly_meeting_target: Optional[int] = None
    price_per_outcome_cents: Optional[int] = None
    monthly_budget_cents: Optional[int] = None
    hitl_threshold: int = 50
    send_gap_seconds: int = 60
    personalize_enabled: bool = False


class CampaignPatch(BaseModel):
    customer_name: Optional[str] = None
    offer: Optional[str] = None
    icp_description: Optional[str] = None
    client_cure: Optional[str] = None
    allowed_signal_types: Optional[list[str]] = None
    booking_url: Optional[str] = None
    status: Optional[str] = None
    monthly_meeting_target: Optional[int] = None
    price_per_outcome_cents: Optional[int] = None
    monthly_budget_cents: Optional[int] = None


def _eng_to_dict(eng, report=None):
    metadata = dict(getattr(eng, "metadata", {}) or {})
    signal_matrix = dict(metadata.get("signal_matrix") or {})
    d = {
        "id": eng.id, "customer_name": eng.customer_name,
        "offer": eng.offer, "icp_description": eng.icp_description,
        "client_cure": metadata.get("client_cure", ""),
        "signal_matrix": signal_matrix,
        "allowed_signal_types": signal_matrix.get("allowed_signal_types", []),
        "deliverability_preflight": metadata.get("deliverability_preflight", {}),
        "booking_url": eng.booking_url, "status": eng.status,
        "monthly_meeting_target": eng.monthly_meeting_target,
        "price_per_outcome_cents": eng.price_per_outcome_cents,
        "monthly_budget_cents": eng.monthly_budget_cents,
        "created_at": eng.created_at.isoformat() if eng.created_at else None,
    }
    if report:
        d["pnl"] = {
            "revenue_cents": report.revenue_cents,
            "cost_cents": report.cost_cents,
            "margin_cents": report.margin_cents,
            "margin_pct": report.margin_pct,
            "cost_by_category_cents": report.cost_by_category_cents,
            "cost_per_qualified_outcome_cents": report.cost_per_qualified_outcome_cents,
            "profit_per_qualified_outcome_cents": report.profit_per_qualified_outcome_cents,
            "budget_remaining_cents": report.budget_remaining_cents,
            "budget_spent_pct": report.budget_spent_pct,
            "over_budget": report.over_budget,
            "booked_count": report.booked_count,
            "qualified_count": report.qualified_count,
        }
    return d


@router.get("")
def list_campaigns(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    pnl=Depends(get_pnl),
):
    engagements = list(store.list_engagements(tenant_id=current_user.tenant_id))
    return [_eng_to_dict(e, pnl.report_for(e.id)) for e in engagements]


@router.post("", status_code=201)
def create_campaign(
    body: CampaignCreate,
    current_user: CurrentUser = Depends(get_current_user),
    ops=Depends(get_ops),
    store=Depends(get_store),
):
    # M5: enforce plan campaign cap.
    from engine.policies import get_plan_limits
    limits = get_plan_limits(current_user.plan)
    existing = [e for e in store.list_engagements(tenant_id=current_user.tenant_id)
                if e.status != "cancelled"]
    if len(existing) >= limits.max_campaigns:
        raise HTTPException(
            403,
            f"Plan '{limits.plan}' allows {limits.max_campaigns} campaign(s). Upgrade to add more.",
        )
    # M5: personalization gated by plan.
    personalize = body.personalize_enabled and limits.personalization

    eng = ops.create_engagement(
        customer_name=body.customer_name,
        offer=body.offer,
        icp_description=body.icp_description,
        booking_url=body.booking_url,
        monthly_meeting_target=body.monthly_meeting_target,
        price_per_outcome_cents=body.price_per_outcome_cents,
        monthly_budget_cents=body.monthly_budget_cents,
    )
    eng = replace(eng, metadata=_campaign_metadata(body))
    store.save_engagement(eng, tenant_id=current_user.tenant_id)

    ops.create_agent(
        engagement_id=eng.id,
        runner_kind="outbound.v1",
        config={
            "hitl_threshold": body.hitl_threshold,
            "send_gap_seconds": body.send_gap_seconds,
            "personalize": personalize,
        },
    )
    return _eng_to_dict(eng)


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    pnl=Depends(get_pnl),
    events=Depends(get_events),
):
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    report = pnl.report_for(campaign_id)
    recent_events = [
        {"kind": e.kind.value, "occurred_at": e.occurred_at.isoformat(),
         "job_id": e.job_id, "prospect_id": e.prospect_id, "payload": dict(e.payload)}
        for e in events.list_recent(engagement_id=campaign_id, limit=25)
    ]
    jobs_awaiting = [
        {"id": j.id, "kind": j.kind.value,
         "to_email": j.payload.get("to_email"), "subject": j.payload.get("subject_template", "")[:60],
         "prospect_id": j.prospect_id}
        for j in store.list_jobs_by_state("awaiting_approval", engagement_id=campaign_id)
    ]
    return {
        **_eng_to_dict(eng, report),
        "agents": [{"id": a.id, "runner_kind": a.runner_kind, "status": a.status, "config": dict(a.config)}
                   for a in store.list_agents(campaign_id)],
        "prospect_count": len(list(store.list_prospects(campaign_id, limit=10_000))),
        "pending_replies": len(list(store.list_replies(campaign_id, status="pending"))),
        "events": recent_events,
        "jobs_awaiting_approval": jobs_awaiting,
    }


@router.patch("/{campaign_id}")
def patch_campaign(
    campaign_id: str,
    body: CampaignPatch,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    from engine.core.types import Engagement as _Eng
    metadata = _patched_campaign_metadata(eng.metadata, body)
    updated = _Eng(
        id=eng.id,
        customer_name=body.customer_name or eng.customer_name,
        offer=body.offer or eng.offer,
        icp_description=body.icp_description or eng.icp_description,
        icp_filters=eng.icp_filters,
        booking_url=body.booking_url if body.booking_url is not None else eng.booking_url,
        monthly_meeting_target=body.monthly_meeting_target if body.monthly_meeting_target is not None else eng.monthly_meeting_target,
        price_per_outcome_cents=body.price_per_outcome_cents if body.price_per_outcome_cents is not None else eng.price_per_outcome_cents,
        monthly_budget_cents=body.monthly_budget_cents if body.monthly_budget_cents is not None else eng.monthly_budget_cents,
        status=body.status or eng.status,
        created_at=eng.created_at,
        metadata=metadata,
    )
    store.save_engagement(updated, tenant_id=current_user.tenant_id)
    return _eng_to_dict(updated)


def _normalize_signal_types(values: list[str] | None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        signal_type = str(value).strip()
        if not signal_type or signal_type in seen:
            continue
        seen.add(signal_type)
        normalized.append(signal_type)
    return normalized


def _campaign_metadata(body: CampaignCreate) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    client_cure = (body.client_cure or "").strip()
    if client_cure:
        metadata["client_cure"] = client_cure
    allowed = _normalize_signal_types(body.allowed_signal_types)
    if allowed:
        metadata["signal_matrix"] = {"allowed_signal_types": allowed}
    return metadata


def _patched_campaign_metadata(existing: Any, body: CampaignPatch) -> dict[str, Any]:
    metadata = dict(existing or {})
    if body.client_cure is not None:
        client_cure = body.client_cure.strip()
        if client_cure:
            metadata["client_cure"] = client_cure
        else:
            metadata.pop("client_cure", None)
    if body.allowed_signal_types is not None:
        allowed = _normalize_signal_types(body.allowed_signal_types)
        if allowed:
            metadata["signal_matrix"] = {"allowed_signal_types": allowed}
        else:
            metadata.pop("signal_matrix", None)
    return metadata


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    from engine.core.types import Engagement as _Eng
    cancelled = _Eng(
        id=eng.id, customer_name=eng.customer_name, offer=eng.offer,
        icp_description=eng.icp_description, icp_filters=eng.icp_filters,
        booking_url=eng.booking_url, monthly_meeting_target=eng.monthly_meeting_target,
        price_per_outcome_cents=eng.price_per_outcome_cents,
        monthly_budget_cents=eng.monthly_budget_cents,
        status="cancelled", created_at=eng.created_at, metadata=eng.metadata,
    )
    store.save_engagement(cancelled, tenant_id=current_user.tenant_id)


@router.post("/{campaign_id}/tick")
def tick_campaign(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    runtime=Depends(get_runtime),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    result = runtime.tick(
        tenant_id=current_user.tenant_id,
        engagement_id=campaign_id,
    )
    return {"ok": True, "result": result}


@router.post("/{campaign_id}/drain")
def drain_campaign(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    runtime=Depends(get_runtime),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    result = runtime.run_once(
        max_iters=20,
        tenant_id=current_user.tenant_id,
        engagement_id=campaign_id,
    )
    return {"ok": True, "result": result}


@router.post("/{campaign_id}/poll-replies")
def poll_replies(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    detector=Depends(get_reply_detector),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    if detector is None:
        raise HTTPException(400, "Gmail reply detector not configured")
    result = detector.poll(campaign_id)
    return {
        "ok": True,
        "prospects_scanned": result.prospects_scanned,
        "replies_recorded": result.replies_recorded,
        "auto_responders": result.auto_responders,
        "token_invalid": result.token_invalid,
        "errors": result.errors[:5],
    }


@router.post("/{campaign_id}/approve-job/{job_id}")
def approve_job(
    campaign_id: str,
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    runtime=Depends(get_runtime),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    ok = runtime.approve_job(
        job_id,
        tenant_id=current_user.tenant_id,
        engagement_id=campaign_id,
    )
    if not ok:
        raise HTTPException(400, "Job not found or not awaiting approval")
    return {"ok": True}


@router.post("/{campaign_id}/reject-job/{job_id}")
def reject_job(
    campaign_id: str,
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    runtime=Depends(get_runtime),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    ok = runtime.reject_job(
        job_id,
        reason="rejected via API",
        tenant_id=current_user.tenant_id,
        engagement_id=campaign_id,
    )
    if not ok:
        raise HTTPException(400, "Job not found or not awaiting approval")
    return {"ok": True}
