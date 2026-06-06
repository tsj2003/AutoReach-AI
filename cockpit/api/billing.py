"""
M5 — Billing / usage API.

GET /api/billing/plan   — current plan + limits
GET /api/billing/usage  — current usage vs limits
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from cockpit.api.deps import get_current_user, get_store
from engine.auth import CurrentUser
from engine.policies import get_plan_limits

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/plan")
def get_plan(current_user: CurrentUser = Depends(get_current_user)):
    limits = get_plan_limits(current_user.plan)
    return {
        "plan": limits.plan,
        "limits": {
            "max_campaigns": limits.max_campaigns,
            "max_mailboxes": limits.max_mailboxes,
            "max_leads_total": limits.max_leads_total,
            "max_emails_per_day": limits.max_emails_per_day,
            "personalization": limits.personalization,
        },
    }


@router.get("/usage")
def get_usage(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    limits = get_plan_limits(current_user.plan)
    engagements = list(store.list_engagements(tenant_id=current_user.tenant_id))
    active = [e for e in engagements if e.status != "cancelled"]
    total_leads = sum(
        len(list(store.list_prospects(e.id, limit=10_000))) for e in active
    )
    return {
        "plan": limits.plan,
        "usage": {
            "campaigns": len(active),
            "campaigns_limit": limits.max_campaigns,
            "leads_total": total_leads,
            "leads_limit": limits.max_leads_total,
        },
    }
