"""
REST API: Contacts (Prospects)

GET    /api/contacts?campaign_id=&cursor=&limit=
POST   /api/contacts
POST   /api/contacts/upload
GET    /api/contacts/{id}
"""

from __future__ import annotations

import io
from typing import Any, Optional

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


@router.get("/summary")
def contacts_summary(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    prospects = list(store.list_prospects(campaign_id, limit=100_000))
    with_email = sum(1 for p in prospects if str(p.email or "").strip())
    discovery = dict((getattr(eng, "metadata", {}) or {}).get("people_discovery") or {})
    return {
        "total": len(prospects),
        "with_email": with_email,
        "without_email": len(prospects) - with_email,
        "people_discovery": discovery,
    }


def _prospect_to_dict(p):
    from engine.signals.catalog import compute_gojiberry_scores

    research = p.research if isinstance(p.research, dict) else {}
    enrichment = research.get("enrichment") if isinstance(research.get("enrichment"), dict) else {}
    enr_fields = enrichment.get("fields") if isinstance(enrichment.get("fields"), dict) else {}
    signals = list(research.get("signals") or [])
    stack = research.get("signal_stack") if isinstance(research.get("signal_stack"), dict) else None
    if not signals and stack and isinstance(stack.get("evidence"), list):
        signals = list(stack.get("evidence") or [])

    fit = research.get("fit") or ("bad_fit" if p.status == "disqualified" else "good_fit")
    scores = compute_gojiberry_scores(
        lead_score=research.get("lead_score"),
        fit_status=fit,
        title=p.title,
        company_name=p.company,
        signals=signals,
        intent_type=research.get("intent_type"),
    )
    return {
        "id": p.id, "engagement_id": p.engagement_id, "email": p.email,
        "email_2": research.get("email_2") or enr_fields.get("email_2"),
        "email_3": research.get("email_3") or enr_fields.get("email_3"),
        "phone": research.get("phone") or enr_fields.get("phone"),
        "phone_2": research.get("phone_2") or enr_fields.get("phone_2"),
        "phone_3": research.get("phone_3") or enr_fields.get("phone_3"),
        "full_name": p.full_name, "company": p.company, "title": p.title,
        "linkedin_url": research.get("linkedin_url") or (p.raw or {}).get("linkedin_url"),
        "location": research.get("location") or (p.raw or {}).get("location"),
        "status": p.status,
        "fit": fit,
        "reject_reason": research.get("reject_reason"),
        "reject_notes": research.get("reject_notes"),
        "bounced": bool(research.get("bounced", False)),
        "unsubscribed": bool(research.get("unsubscribed", False)),
        "red_listed": bool(research.get("red_listed", False)),
        "blocked": bool(research.get("blocked", False)),
        "company_blocked": bool(research.get("company_blocked", False)),
        "enriching_email": bool(research.get("enriching_email", False)),
        "enriching_phone": bool(research.get("enriching_phone", False)),
        "scoring": research.get("scoring", scores["scoring"]),
        "intent_scoring": research.get("intent_scoring", scores["intent_scoring"]),
        "total_scoring": research.get("total_scoring", scores["total_scoring"]),
        "score_reasoning": research.get("score_reasoning", scores["score_reasoning"]),
        "intent": scores["intent"],
        "intent_type": scores["intent_type"],
        "intent_keyword": scores["intent_keyword"],
        "signals": signals,
        # US-003: expose the buying-signal stack (score + cited evidence) so the
        # UI can show WHY this prospect exists.
        "signal_stack": stack,
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
    from engine.policies import assert_under_lead_cap

    assert_under_lead_cap(
        store, tenant_id=current_user.tenant_id, plan=current_user.plan, delta=1,
    )
    from engine.services.accounts import normalize_company_domain, upsert_account

    domain = normalize_company_domain(body.company) or (
        body.email.split("@", 1)[1] if body.email and "@" in body.email else None
    )
    account = upsert_account(
        store,
        tenant_id=current_user.tenant_id,
        engagement_id=body.campaign_id,
        company_domain=domain or "",
        company_name=body.company,
    )
    p = ops.add_prospect(
        engagement_id=body.campaign_id,
        email=body.email.strip().lower(),
        full_name=body.full_name,
        company=body.company,
        title=body.title,
    )
    if account is not None:
        from engine.core.types import Prospect
        research = dict(p.research or {})
        research["account_id"] = account.id
        research["company_domain"] = account.company_domain
        p = Prospect(
            id=p.id, engagement_id=p.engagement_id, email=p.email,
            full_name=p.full_name, company=p.company, title=p.title,
            raw=dict(p.raw or {}), research=research, status=p.status,
            created_at=p.created_at,
        )
        store.save_prospect(p, tenant_id=current_user.tenant_id)
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

    # Soft pre-check: row count upper-bounds new leads; empty lines inflate slightly.
    approx_rows = max(0, len([ln for ln in text.splitlines() if ln.strip()]) - 1)
    from engine.policies import assert_under_lead_cap

    assert_under_lead_cap(
        store,
        tenant_id=current_user.tenant_id,
        plan=current_user.plan,
        delta=max(1, approx_rows),
    )

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



class AttachContactSignalRequest(BaseModel):
    signal_type: str = "SEARCH_KEYWORD"
    title: Optional[str] = None
    description: Optional[str] = None
    intent: Optional[str] = None
    intent_keyword: Optional[str] = None
    source_url: Optional[str] = None
    confidence: Optional[float] = None
    lead_score: Optional[float] = None


class RejectContactRequest(BaseModel):
    reason: str
    fit: str = "bad_fit"
    notes: Optional[str] = None


@router.post("/{prospect_id}/signals")
def attach_contact_signal(
    prospect_id: str,
    body: AttachContactSignalRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    """Attach a Gojiberry buying signal to a contact and recompute dual-axis scores."""
    from datetime import datetime, timezone
    from engine.core.types import Prospect
    from engine.signals.catalog import compute_gojiberry_scores, resolve_signal_type

    p = store.get_prospect(prospect_id)
    if not p:
        raise HTTPException(404, "Contact not found")
    eng = store.get_engagement(p.engagement_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(403, "Access denied")

    resolved = resolve_signal_type(body.signal_type)
    canonical_code = resolved.code if resolved else body.signal_type.strip().upper()
    research = dict(p.research or {})
    signals = list(research.get("signals") or [])
    sig_entry = {
        "signal_type": canonical_code,
        "name": resolved.name if resolved else canonical_code,
        "intent_points": resolved.intent_points if resolved else 2,
        "title": body.title or body.intent or (resolved.name if resolved else canonical_code),
        "description": body.description or body.intent or "",
        "intent": body.intent or body.title or (resolved.name if resolved else canonical_code),
        "intent_keyword": body.intent_keyword,
        "confidence": body.confidence if body.confidence is not None else 0.88,
        "source_url": body.source_url,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    signals.append(sig_entry)
    research["signals"] = signals
    if body.lead_score is not None:
        research["lead_score"] = body.lead_score

    scores = compute_gojiberry_scores(
        lead_score=research.get("lead_score"),
        fit_status=research.get("fit"),
        title=p.title,
        company_name=p.company,
        signals=signals,
        intent_type=canonical_code,
    )
    research.update(scores)

    updated = Prospect(
        id=p.id,
        engagement_id=p.engagement_id,
        email=p.email,
        full_name=p.full_name,
        company=p.company,
        title=p.title,
        raw=dict(p.raw or {}),
        research=research,
        status=p.status,
        created_at=p.created_at,
    )
    store.save_prospect(updated, tenant_id=current_user.tenant_id)
    return _prospect_to_dict(updated)


@router.post("/{prospect_id}/reject")
def reject_contact(
    prospect_id: str,
    body: RejectContactRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    """Reject or update fit status of a contact with Gojiberry's 10 ContactRejectReason codes."""
    from datetime import datetime, timezone
    from engine.core.types import Prospect
    from engine.signals.catalog import VALID_REJECT_REASON_CODES, compute_gojiberry_scores

    p = store.get_prospect(prospect_id)
    if not p:
        raise HTTPException(404, "Contact not found")
    eng = store.get_engagement(p.engagement_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(403, "Access denied")

    reason_code = body.reason.strip().lower()
    if reason_code not in VALID_REJECT_REASON_CODES:
        raise HTTPException(
            400,
            f"Invalid reject reason '{body.reason}'. Allowed: {sorted(VALID_REJECT_REASON_CODES)}",
        )
    fit_state = body.fit.strip().lower()
    if fit_state not in ("good_fit", "bad_fit", "pending"):
        raise HTTPException(400, "fit must be one of: good_fit, bad_fit, pending")

    research = dict(p.research or {})
    research["fit"] = fit_state
    research["reject_reason"] = reason_code
    research["reject_notes"] = body.notes
    research["rejected_at"] = datetime.now(timezone.utc).isoformat()

    scores = compute_gojiberry_scores(
        lead_score=research.get("lead_score"),
        fit_status=fit_state,
        title=p.title,
        company_name=p.company,
        signals=research.get("signals") or [],
    )
    research.update(scores)

    new_status = "disqualified" if fit_state == "bad_fit" else p.status
    updated = Prospect(
        id=p.id,
        engagement_id=p.engagement_id,
        email=p.email,
        full_name=p.full_name,
        company=p.company,
        title=p.title,
        raw=dict(p.raw or {}),
        research=research,
        status=new_status,
        created_at=p.created_at,
    )
    store.save_prospect(updated, tenant_id=current_user.tenant_id)
    return _prospect_to_dict(updated)
