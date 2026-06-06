"""
Meetings — the OaaS billing ledger.

    GET  /engagements/{eng}/meetings                  list + P&L
    POST /engagements/{eng}/meetings                  book one
    POST /meetings/{id}/status                        qualify / no_show / cancel
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


def _parse_local_dt(value: str) -> datetime:
    """Parse an HTML datetime-local value (YYYY-MM-DDTHH:MM) as UTC."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)


@router.get(
    "/engagements/{engagement_id}/meetings",
    response_class=HTMLResponse,
)
def list_meetings(request: Request, engagement_id: str):
    store = request.app.state.store
    ops = request.app.state.ops
    pnl = request.app.state.pnl
    eng = store.get_engagement(engagement_id)
    if eng is None:
        raise HTTPException(404, "engagement not found")
    meetings = list(ops.list_meetings(engagement_id, limit=200))
    enriched = []
    for m in meetings:
        p = store.get_prospect(m.prospect_id)
        enriched.append({"meeting": m, "prospect": p})
    report = pnl.report_for(engagement_id)
    return request.app.state.templates.TemplateResponse(
        request,
        "meetings/list.html",
        {
            "engagement": eng,
            "meetings": enriched,
            "report": report,
        },
    )


@router.post("/engagements/{engagement_id}/meetings")
def book_meeting(
    request: Request,
    engagement_id: str,
    prospect_id: str = Form(...),
    scheduled_for: str = Form(...),  # html datetime-local
    notes: str = Form(""),
    reply_id: str = Form(""),
):
    when = _parse_local_dt(scheduled_for)
    request.app.state.ops.book_meeting(
        engagement_id=engagement_id,
        prospect_id=prospect_id.strip(),
        scheduled_for=when,
        reply_id=reply_id.strip() or None,
        notes=notes.strip(),
    )
    return RedirectResponse(
        url=f"/engagements/{engagement_id}/meetings", status_code=303
    )


@router.post("/meetings/{meeting_id}/status")
def update_status(
    request: Request,
    meeting_id: str,
    status: str = Form(...),
    notes: str = Form(""),
):
    ops = request.app.state.ops
    meeting = request.app.state.store.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(404, "meeting not found")
    if not ops.update_meeting_status(meeting_id, status=status, notes=notes or None):
        raise HTTPException(400, "invalid status")
    return RedirectResponse(
        url=f"/engagements/{meeting.engagement_id}/meetings", status_code=303
    )
