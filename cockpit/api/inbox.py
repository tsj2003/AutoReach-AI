"""
REST API: Inbox (Replies)

GET  /api/inbox?campaign_id=&status=
POST /api/inbox/{reply_id}/approve
POST /api/inbox/{reply_id}/discard
POST /api/inbox/{reply_id}/regenerate-draft
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from cockpit.api.deps import get_current_user, get_ops, get_store
from engine.auth import CurrentUser

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


def _reply_to_dict(r, prospect=None):
    return {
        "id": r.id, "engagement_id": r.engagement_id,
        "prospect_id": r.prospect_id,
        "prospect_email": prospect.email if prospect else None,
        "prospect_company": prospect.company if prospect else None,
        "snippet": r.snippet, "classification": r.classification,
        "suggested_reply": r.suggested_reply, "status": r.status,
        "received_at": r.received_at.isoformat() if r.received_at else None,
    }


@router.get("")
def list_inbox(
    campaign_id: str,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    replies = list(ops.list_replies(campaign_id, status=status, limit=limit))
    return [_reply_to_dict(r, store.get_prospect(r.prospect_id)) for r in replies]


@router.post("/{reply_id}/approve")
def approve_reply(
    reply_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    reply = store.get_reply(reply_id)
    if not reply:
        raise HTTPException(404, "Reply not found")
    if not store.get_engagement(reply.engagement_id, tenant_id=current_user.tenant_id):
        raise HTTPException(403, "Access denied")
    if not ops.mark_reply_sent(reply_id):
        raise HTTPException(400, "Cannot mark this reply as sent")
    return {"ok": True}


@router.post("/{reply_id}/discard")
def discard_reply(
    reply_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    reply = store.get_reply(reply_id)
    if not reply:
        raise HTTPException(404, "Reply not found")
    if not store.get_engagement(reply.engagement_id, tenant_id=current_user.tenant_id):
        raise HTTPException(403, "Access denied")
    ops.discard_reply(reply_id)
    return {"ok": True}


@router.post("/{reply_id}/regenerate-draft")
def regenerate_draft(
    reply_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    """Re-run Gemini classification + draft on an existing reply."""
    reply = store.get_reply(reply_id)
    if not reply:
        raise HTTPException(404, "Reply not found")
    eng = store.get_engagement(reply.engagement_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(403, "Access denied")

    from engine.llm.classifier import classify_and_draft
    from engine.llm import GeminiClient

    result = classify_and_draft(
        snippet=reply.snippet,
        booking_url=eng.booking_url or "",
        client=GeminiClient(),
    )
    updated = ops.update_reply_draft(reply_id, suggested_reply=result.suggested_reply)
    return {
        "ok": True,
        "classification": result.classification,
        "suggested_reply": result.suggested_reply,
        "fallback_used": result.fallback_used,
    }
