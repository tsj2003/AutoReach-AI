"""
REST API: Contacts (Prospects)

GET    /api/contacts?campaign_id=&cursor=&limit=
POST   /api/contacts
POST   /api/contacts/upload
GET    /api/contacts/{id}
"""

from __future__ import annotations

import io
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from cockpit.api.deps import get_csv_ingest, get_current_user, get_ops, get_store
from engine.auth import CurrentUser

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


class ContactCreate(BaseModel):
    campaign_id: str
    email: str
    full_name: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None


def _prospect_to_dict(p):
    return {
        "id": p.id, "engagement_id": p.engagement_id, "email": p.email,
        "full_name": p.full_name, "company": p.company, "title": p.title,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("")
def list_contacts(
    campaign_id: str,
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    status: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")

    items, next_cursor = store.list_prospects_cursor(
        campaign_id,
        cursor=cursor,
        limit=limit,
        tenant_id=None,  # M10: tenant_id filter not required for cursor list
    )
    return {
        "data": [_prospect_to_dict(p) for p in items],
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
    }


@router.post("", status_code=201)
def create_contact(
    body: ContactCreate,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    if not store.get_engagement(body.campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    p = ops.add_prospect(
        engagement_id=body.campaign_id,
        email=body.email.strip().lower(),
        full_name=body.full_name,
        company=body.company,
        title=body.title,
    )
    return _prospect_to_dict(p)


@router.post("/upload")
async def upload_contacts(
    campaign_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    csv_ingest=Depends(get_csv_ingest),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    result = csv_ingest.ingest_text(engagement_id=campaign_id, text=text)
    return {
        "total_rows": result.total_rows,
        "loaded": result.loaded,
        "skipped_invalid_email": result.skipped_invalid_email,
        "skipped_duplicates": result.skipped_duplicates,
        "skipped_existing": result.skipped_existing,
        "errors": result.errors,
    }


@router.get("/{prospect_id}")
def get_contact(
    prospect_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    p = store.get_prospect(prospect_id)
    if not p:
        raise HTTPException(404, "Contact not found")
    eng = store.get_engagement(p.engagement_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(403, "Access denied")
    return _prospect_to_dict(p)
