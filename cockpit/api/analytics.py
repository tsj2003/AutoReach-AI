"""
REST API: Analytics

GET /api/analytics/dashboard  — aggregate stats across all tenant campaigns
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from cockpit.api.deps import get_current_user, get_pnl, get_store
from engine.auth import CurrentUser

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/dashboard")
def dashboard(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    pnl=Depends(get_pnl),
):
    engagements = list(store.list_engagements(tenant_id=current_user.tenant_id))
    totals = {
        "campaigns": len(engagements),
        "active_campaigns": sum(1 for e in engagements if e.status == "active"),
        "total_revenue_cents": 0,
        "total_cost_cents": 0,
        "total_margin_cents": 0,
        "total_booked": 0,
        "total_qualified": 0,
        "cost_by_category_cents": {},
    }
    campaign_summaries = []
    for eng in engagements:
        report = pnl.report_for(eng.id)
        if report:
            totals["total_revenue_cents"] += report.revenue_cents
            totals["total_cost_cents"] += report.cost_cents
            totals["total_margin_cents"] += report.margin_cents
            totals["total_booked"] += report.booked_count
            totals["total_qualified"] += report.qualified_count
            for category, amount_cents in report.cost_by_category_cents.items():
                totals["cost_by_category_cents"][category] = (
                    totals["cost_by_category_cents"].get(category, 0) + amount_cents
                )
        campaign_summaries.append({
            "id": eng.id,
            "name": eng.customer_name,
            "status": eng.status,
            "revenue_cents": report.revenue_cents if report else 0,
            "cost_cents": report.cost_cents if report else 0,
            "margin_cents": report.margin_cents if report else 0,
            "cost_per_qualified_outcome_cents": (
                report.cost_per_qualified_outcome_cents if report else None
            ),
            "qualified": report.qualified_count if report else 0,
        })

    return {
        "totals": totals,
        "campaigns": campaign_summaries,
    }
