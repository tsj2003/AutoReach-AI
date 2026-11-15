"""
REST API: Inbox (Replies)

GET  /api/inbox?campaign_id=&status=
POST /api/inbox/{reply_id}/approve
POST /api/inbox/{reply_id}/discard
POST /api/inbox/{reply_id}/regenerate-draft
POST /api/inbox/{reply_id}/book-meeting
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from cockpit.api.deps import get_current_user, get_events, get_ledger, get_ops, get_store
from engine.auth import CurrentUser

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


class SendReplyRequest(BaseModel):
    body_text: Optional[str] = None
    channel: Optional[str] = None
    split_into_parts: bool = False


def _split_into_bubbles(text: str) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    if len(paragraphs) > 1:
        return paragraphs[:4]
    sentences = [s.strip() for s in cleaned.replace("? ", "?\n").replace(". ", ".\n").splitlines() if s.strip()]
    return sentences[:4] if sentences else [cleaned]


def _reply_to_dict(r, prospect=None):
    cls_lower = (r.classification or "").lower()
    if cls_lower in ("interested", "positive", "meeting_request", "hot"):
        interested = True
        interested_reasoning = "Prospect expressed direct buying or meeting interest in their reply."
    elif cls_lower in ("not_interested", "unsubscribe", "negative", "out_of_office"):
        interested = False
        interested_reasoning = f"Classified as '{cls_lower}' — low immediate conversion intent."
    else:
        interested = None
        interested_reasoning = "Neutral or clarifying question — requires follow-up."

    research = dict(getattr(prospect, "research", None) or {}) if prospect else {}
    channel = research.get("last_channel") or ("linkedin" if "linkedin" in (r.snippet or "").lower() else "email")
    ai_draft = r.suggested_reply or (
        f"Hi {(prospect.full_name or 'there').split()[0]}, thanks for the note! "
        "Happy to share more context — would Thursday at 2pm work for a quick 15-min chat?"
        if prospect
        else "Thanks for getting back to me! Would Thursday work for a quick 15-minute chat?"
    )
    parts = _split_into_bubbles(ai_draft)

    raw = dict(getattr(prospect, "raw", None) or {}) if prospect else {}
    return {
        "id": r.id,
        "engagement_id": r.engagement_id,
        "prospect_id": r.prospect_id,
        "prospect_name": prospect.full_name if prospect else None,
        "prospect_email": prospect.email if prospect else None,
        "prospect_company": prospect.company if prospect else None,
        "prospect_title": prospect.title if prospect else None,
        "channel": channel,
        "snippet": r.snippet,
        "classification": r.classification,
        "interested": interested,
        "interested_reasoning": interested_reasoning,
        "suggested_reply": r.suggested_reply,
        "ai_generated_reply": ai_draft,
        "parts": parts,
        "status": r.status,
        "received_at": r.received_at.isoformat() if r.received_at else None,
        "meeting_booked_at": raw.get("meeting_booked_at"),
        "gcal_event_id": raw.get("gcal_event_id"),
        "meet_link": raw.get("meet_link"),
        "gcal_html_link": raw.get("gcal_html_link"),
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
    events=Depends(get_events),
    ledger=Depends(get_ledger),
):
    reply = store.get_reply(reply_id)
    if not reply:
        raise HTTPException(404, "Reply not found")
    if not store.get_engagement(reply.engagement_id, tenant_id=current_user.tenant_id):
        raise HTTPException(403, "Access denied")
    if reply.status == "sent":
        return {"ok": True, "sent": True, "already_sent": True}

    body = (reply.suggested_reply or "").strip()
    if not body:
        raise HTTPException(400, "No suggested reply to send")

    from engine.services.reply_sender import ReplySender

    sender = ReplySender(store=store, events=events, ledger=ledger)
    if not sender.send(reply, body, tenant_id=current_user.tenant_id):
        raise HTTPException(502, "Failed to send reply via mailbox — check mailbox connection")

    if not ops.mark_reply_sent(reply_id):
        raise HTTPException(400, "Cannot mark this reply as sent")
    return {"ok": True, "sent": True}


@router.post("/{reply_id}/send")
def send_custom_reply(
    reply_id: str,
    payload: Optional[SendReplyRequest] = None,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
    events=Depends(get_events),
    ledger=Depends(get_ledger),
):
    """1-click send or approve an Unibox 2.0 reply (supports edited body_text and multi-bubble parts)."""
    reply = store.get_reply(reply_id)
    if not reply:
        raise HTTPException(404, "Reply not found")
    if not store.get_engagement(reply.engagement_id, tenant_id=current_user.tenant_id):
        raise HTTPException(403, "Access denied")
    if reply.status == "sent":
        return {"ok": True, "sent": True, "already_sent": True}

    body_text = ((payload.body_text if payload else None) or reply.suggested_reply or "").strip()
    if not body_text:
        raise HTTPException(400, "No reply body provided")

    if payload and payload.body_text:
        ops.update_reply_draft(reply_id, suggested_reply=body_text)

    from engine.services.reply_sender import ReplySender

    sender = ReplySender(store=store, events=events, ledger=ledger)
    sent_via_mailbox = sender.send(reply, body_text, tenant_id=current_user.tenant_id)
    ops.mark_reply_sent(reply_id)
    return {
        "ok": True,
        "sent": True,
        "via_mailbox": sent_via_mailbox,
        "parts": _split_into_bubbles(body_text),
    }


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




class BookMeetingRequest(BaseModel):
    start_iso: Optional[str] = None
    end_iso: Optional[str] = None
    timezone: Optional[str] = "America/New_York"
    title: Optional[str] = None
    description: Optional[str] = None
    create_meet: bool = True
    mailbox_id: Optional[str] = None


@router.post("/{reply_id}/book-meeting")
def book_meeting_from_reply(
    reply_id: str,
    body: Optional[BookMeetingRequest] = None,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    """Book a Google Calendar event for an interested / meeting-intent reply.

    If start_iso is omitted, picks the next free 30-minute slot from freebusy.
    Persists meeting_booked_at / gcal_event_id / meet_link on prospect.raw and
    creates an engine Meeting row.
    """
    from datetime import datetime, timedelta, timezone

    from engine.core.types import Prospect
    from engine.services.google_calendar import (
        CalendarApiError,
        CalendarNotConnected,
        GoogleCalendarService,
    )

    body = body or BookMeetingRequest()
    reply = store.get_reply(reply_id)
    if not reply:
        raise HTTPException(404, "Reply not found")
    eng = store.get_engagement(reply.engagement_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(403, "Access denied")

    cls = (reply.classification or "").lower()
    if cls in ("unsubscribe", "do_not_contact", "not_interested", "auto"):
        raise HTTPException(400, f"Cannot book meeting for classification '{cls}'")

    prospect = store.get_prospect(reply.prospect_id)
    if not prospect or not prospect.email:
        raise HTTPException(400, "Prospect email required to send Calendar invite")

    raw = dict(prospect.raw or {})
    if raw.get("gcal_event_id"):
        return {
            "ok": True,
            "already_booked": True,
            "gcal_event_id": raw.get("gcal_event_id"),
            "meet_link": raw.get("meet_link"),
            "gcal_html_link": raw.get("gcal_html_link"),
            "meeting_booked_at": raw.get("meeting_booked_at"),
        }

    svc = GoogleCalendarService(
        store=store,
        tenant_id=current_user.tenant_id,
        mailbox_id=body.mailbox_id,
    )
    tz = body.timezone or "America/New_York"
    start_iso = body.start_iso
    end_iso = body.end_iso
    try:
        if not start_iso:
            slots = svc.list_free_slots(
                days=7, slot_minutes=30, max_slots=1, timezone_name=tz
            )
            if not slots:
                raise HTTPException(409, "No open Calendar slots in the next 7 working days")
            start_iso = slots[0].start.isoformat()
            end_iso = slots[0].end.isoformat()
        elif not end_iso:
            start_dt = datetime.fromisoformat(
                start_iso.replace("Z", "+00:00") if start_iso.endswith("Z") else start_iso
            )
            end_iso = (start_dt + timedelta(minutes=30)).isoformat()

        booked = svc.book_event(
            prospect_email=prospect.email,
            prospect_name=prospect.full_name or "",
            start_iso=start_iso,
            end_iso=end_iso,
            title=body.title or f"Attainly intro — {prospect.full_name or prospect.email}",
            description=body.description or (
                f"Booked from Attainly Unibox reply ({reply.classification})."
            ),
            timezone_name=tz,
            create_meet=body.create_meet,
        )
    except HTTPException:
        raise
    except CalendarNotConnected as exc:
        raise HTTPException(409, str(exc)) from exc
    except CalendarApiError as exc:
        raise HTTPException(502, str(exc)) from exc

    start_dt = datetime.fromisoformat(
        booked.start_iso.replace("Z", "+00:00")
        if booked.start_iso.endswith("Z")
        else booked.start_iso
    )
    notes = (
        f"gcal_event_id={booked.event_id}; meet_link={booked.meet_link}; "
        f"html_link={booked.html_link}"
    )
    meeting = ops.book_meeting(
        engagement_id=reply.engagement_id,
        prospect_id=reply.prospect_id,
        scheduled_for=start_dt,
        reply_id=reply.id,
        notes=notes,
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    raw["meeting_booked_at"] = now_iso
    raw["gcal_event_id"] = booked.event_id
    raw["meet_link"] = booked.meet_link
    raw["gcal_html_link"] = booked.html_link
    store.save_prospect(
        Prospect(
            id=prospect.id,
            engagement_id=prospect.engagement_id,
            email=prospect.email,
            full_name=prospect.full_name,
            company=prospect.company,
            title=prospect.title,
            raw=raw,
            research=prospect.research,
            status="booked",
            created_at=prospect.created_at,
        )
    )

    confirm = (
        f"You're all set — I booked us for a quick intro. "
        f"Calendar invite is on its way"
        + (f" (Meet: {booked.meet_link})" if booked.meet_link else "")
        + "."
    )
    ops.update_reply_draft(reply_id, suggested_reply=confirm)

    payload = booked.to_dict()
    return {
        "ok": True,
        "meeting_id": meeting.id,
        "meeting_booked_at": now_iso,
        "suggested_reply": confirm,
        "gcal_event_id": payload.get("event_id"),
        "gcal_html_link": payload.get("html_link"),
        **payload,
    }


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
    from engine.services.google_calendar import (
        CalendarNotConnected,
        GoogleCalendarService,
        format_slots_for_reply,
    )

    proposed_slots = ""
    booking_url = eng.booking_url or ""
    try:
        cal = GoogleCalendarService(store=store, tenant_id=current_user.tenant_id)
        slots = cal.list_free_slots(days=7, slot_minutes=30, max_slots=3)
        proposed_slots = format_slots_for_reply(slots)
    except (CalendarNotConnected, Exception):
        proposed_slots = ""

    result = classify_and_draft(
        snippet=reply.snippet,
        booking_url=booking_url,
        proposed_slots=proposed_slots,
        client=GeminiClient(),
    )
    updated = ops.update_reply_draft(reply_id, suggested_reply=result.suggested_reply)
    return {
        "ok": True,
        "classification": result.classification,
        "suggested_reply": result.suggested_reply,
        "fallback_used": result.fallback_used,
    }
