"""
REST API: Meetings

GET  /api/meetings?campaign_id=
POST /api/meetings
POST /api/meetings/{id}/status
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cockpit.api.deps import get_current_user, get_ops, get_store
from engine.auth import CurrentUser

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


class MeetingCreate(BaseModel):
    campaign_id: str
    prospect_id: str
    scheduled_for: datetime
    reply_id: Optional[str] = None
    notes: str = ""


class MeetingStatusUpdate(BaseModel):
    status: str  # booked | qualified | no_show | cancelled
    notes: Optional[str] = None


def _meeting_to_dict(m, prospect=None):
    return {
        "id": m.id, "engagement_id": m.engagement_id,
        "prospect_id": m.prospect_id, "reply_id": m.reply_id,
        "scheduled_for": m.scheduled_for.isoformat() if m.scheduled_for else None,
        "status": m.status, "notes": m.notes,
        "booked_at": m.booked_at.isoformat() if m.booked_at else None,
        "prospect_email": prospect.email if prospect else None,
        "prospect_company": prospect.company if prospect else None,
    }


@router.get("")
def list_meetings(
    campaign_id: str,
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    meetings = list(ops.list_meetings(campaign_id, status=status))
    return [_meeting_to_dict(m, store.get_prospect(m.prospect_id)) for m in meetings]


@router.post("", status_code=201)
def create_meeting(
    body: MeetingCreate,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    if not store.get_engagement(body.campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    scheduled = body.scheduled_for
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    m = ops.book_meeting(
        engagement_id=body.campaign_id,
        prospect_id=body.prospect_id,
        scheduled_for=scheduled,
        reply_id=body.reply_id,
        notes=body.notes,
    )
    return _meeting_to_dict(m)


@router.post("/{meeting_id}/status")
def update_meeting_status(
    meeting_id: str,
    body: MeetingStatusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    m = store.get_meeting(meeting_id)
    if not m:
        raise HTTPException(404, "Meeting not found")
    if not store.get_engagement(m.engagement_id, tenant_id=current_user.tenant_id):
        raise HTTPException(403, "Access denied")
    if not ops.update_meeting_status(meeting_id, status=body.status, notes=body.notes):
        raise HTTPException(400, "Invalid status value")
    return {"ok": True}
