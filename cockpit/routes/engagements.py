"""
Engagements + dashboard routes.

    GET  /engagements                list + per-eng P&L summary
    GET  /engagements/new            form
    POST /engagements                create
    GET  /engagements/{id}           detail (events, jobs, costs, P&L)
    POST /engagements/{id}/pause     pause
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from engine.services import OperationsService, PnLService

router = APIRouter()


def _ops(request: Request) -> OperationsService:
    return request.app.state.ops


def _pnl(request: Request) -> PnLService:
    return request.app.state.pnl


@router.get("/engagements", response_class=HTMLResponse)
def list_engagements(request: Request):
    engagements = _ops(request).list_engagements()
    pnl = _pnl(request)
    rows = [
        {"engagement": e, "report": pnl.report_for(e.id)}
        for e in engagements
    ]
    return request.app.state.templates.TemplateResponse(
        request,
        "engagements/list.html",
        {"rows": rows},
    )


@router.get("/engagements/new", response_class=HTMLResponse)
def new_engagement_form(request: Request):
    return request.app.state.templates.TemplateResponse(
        request, "engagements/new.html", {}
    )


@router.post("/engagements")
def create_engagement(
    request: Request,
    customer_name: str = Form(...),
    offer: str = Form(...),
    icp_description: str = Form(...),
    booking_url: str = Form(""),
    monthly_meeting_target: int = Form(0),
    price_per_outcome_cents: int = Form(0),
    monthly_budget_cents: int = Form(0),
):
    ops = _ops(request)
    eng = ops.create_engagement(
        customer_name=customer_name.strip(),
        offer=offer.strip(),
        icp_description=icp_description.strip(),
        booking_url=booking_url.strip() or None,
        monthly_meeting_target=monthly_meeting_target or None,
        price_per_outcome_cents=price_per_outcome_cents or None,
        monthly_budget_cents=monthly_budget_cents or None,
    )
    # Default agent so the engagement is immediately usable.
    ops.create_agent(
        engagement_id=eng.id,
        runner_kind="outbound.v1",
        config={"hitl_threshold": 50, "send_gap_seconds": 60},
    )
    return RedirectResponse(url=f"/engagements/{eng.id}", status_code=303)


@router.get("/engagements/{engagement_id}", response_class=HTMLResponse)
def engagement_detail(request: Request, engagement_id: str):
    store = request.app.state.store
    events = request.app.state.events
    ledger = request.app.state.ledger
    ops = _ops(request)
    pnl = _pnl(request)

    eng = store.get_engagement(engagement_id)
    if eng is None:
        raise HTTPException(404, "engagement not found")

    agents = list(store.list_agents(engagement_id))
    prospect_count = len(list(ops.list_prospects(engagement_id, limit=10_000)))
    pending_replies = len(list(ops.list_replies(engagement_id, status="pending", limit=10_000)))

    job_states = ["awaiting_approval", "pending", "running", "succeeded", "failed", "dead_lettered"]
    jobs_by_state = {
        s: list(store.list_jobs_by_state(s, engagement_id=engagement_id, limit=20))
        for s in job_states
    }
    recent_events = list(events.list_recent(engagement_id=engagement_id, limit=25))
    report = pnl.report_for(engagement_id)

    return request.app.state.templates.TemplateResponse(
        request,
        "engagements/detail.html",
        {
            "engagement": eng,
            "agents": agents,
            "prospect_count": prospect_count,
            "pending_replies": pending_replies,
            "jobs_by_state": jobs_by_state,
            "recent_events": recent_events,
            "report": report,
        },
    )


@router.post("/engagements/{engagement_id}/pause")
def pause_engagement(request: Request, engagement_id: str):
    if not _ops(request).pause_engagement(engagement_id):
        raise HTTPException(400, "engagement could not be paused")
    return RedirectResponse(url=f"/engagements/{engagement_id}", status_code=303)
