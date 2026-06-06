"""
M7 — Orphaned replies API.

GET  /api/inbox/others             — unmatched replies (forwards, colleague replies)
POST /api/inbox/others/{id}/attach — link to an existing prospect
POST /api/inbox/others/{id}/ignore — mark ignored
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cockpit.api.deps import get_current_user, get_store
from engine.auth import CurrentUser

router = APIRouter(prefix="/api/inbox/others", tags=["orphaned"])


class AttachRequest(BaseModel):
    prospect_id: str


@router.get("")
def list_orphaned(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    return store.list_orphaned_replies(current_user.tenant_id, status="unmatched")


@router.post("/{orphan_id}/attach")
def attach(
    orphan_id: str,
    body: AttachRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    prospect = store.get_prospect(body.prospect_id)
    if not prospect:
        raise HTTPException(404, "Prospect not found")
    eng = store.get_engagement(prospect.engagement_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(403, "Access denied")
    if not store.attach_orphaned_reply(orphan_id, body.prospect_id):
        raise HTTPException(404, "Orphaned reply not found")
    return {"ok": True}
