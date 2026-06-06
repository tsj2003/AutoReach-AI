"""
M11 — Cal.com webhook → auto-book meeting.

Cal.com sends a POST to this endpoint when a booking is created, rescheduled,
or cancelled. We verify the HMAC signature, parse the booking, match the
prospect by email, and call `ops.book_meeting()`.

Environment variables
---------------------
    CALCOM_WEBHOOK_SECRET   — the secret set in Cal.com dashboard
                              (Settings → Webhooks → secret)
    If not set, signature verification is skipped (dev only — always warn).

Cal.com payload shape (simplified)
------------------------------------
{
  "triggerEvent": "BOOKING_CREATED" | "BOOKING_RESCHEDULED" | "BOOKING_CANCELLED",
  "payload": {
    "uid": "...",
    "title": "...",
    "startTime": "2026-06-01T15:00:00Z",
    "attendees": [
      {"email": "prospect@example.com", "name": "Prospect Name"}
    ],
    "organizer": {"email": "you@example.com"}
  }
}
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SUPPORTED_TRIGGERS = {"BOOKING_CREATED", "BOOKING_RESCHEDULED", "BOOKING_CANCELLED"}


def _verify_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """Verify Cal.com HMAC-SHA256 signature."""
    if not signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.lower().replace("sha256=", ""))


@router.post("/calcom/booking")
async def calcom_booking_webhook(
    request: Request,
    x_cal_signature_256: str | None = Header(default=None, alias="X-Cal-Signature-256"),
):
    """
    Receive Cal.com booking events and create/update Meeting records.
    """
    body = await request.body()
    webhook_secret = os.getenv("CALCOM_WEBHOOK_SECRET", "").strip()

    # Signature verification
    if webhook_secret:
        if not _verify_signature(body, x_cal_signature_256, webhook_secret):
            logger.warning("Cal.com webhook signature mismatch — request rejected")
            raise HTTPException(401, "Invalid webhook signature")
    else:
        logger.warning(
            "CALCOM_WEBHOOK_SECRET not set — skipping signature verification (dev only)"
        )

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(400, f"Invalid JSON payload: {exc}")

    trigger = str(payload.get("triggerEvent", "")).upper()
    if trigger not in SUPPORTED_TRIGGERS:
        # Unknown trigger — ack and ignore.
        return JSONResponse({"ok": True, "ignored": True, "trigger": trigger})

    booking = payload.get("payload", {}) or {}
    start_time_raw = booking.get("startTime")
    attendees = booking.get("attendees") or []
    booking_uid = booking.get("uid", "")
    title = booking.get("title", "")

    if not attendees or not start_time_raw:
        raise HTTPException(400, "Missing attendees or startTime in payload")

    # Parse start time — Cal.com sends ISO 8601 UTC.
    try:
        if start_time_raw.endswith("Z"):
            start_time_raw = start_time_raw[:-1] + "+00:00"
        scheduled_for = datetime.fromisoformat(start_time_raw).astimezone(timezone.utc)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, f"Invalid startTime format: {exc}")

    ops = request.app.state.ops
    store = request.app.state.store

    # Find the prospect by attendee email across all active engagements.
    attendee_emails = [a.get("email", "").strip().lower() for a in attendees if a.get("email")]

    if trigger == "BOOKING_CANCELLED":
        return _handle_cancellation(store, ops, attendee_emails, booking_uid)

    if trigger == "BOOKING_RESCHEDULED":
        # Treat rescheduled as cancel old + create new (simpler state).
        _handle_cancellation(store, ops, attendee_emails, booking_uid)
        # Fall through to create the new booking.

    # BOOKING_CREATED (or rescheduled-new)
    booked = []
    for email in attendee_emails:
        # Search all engagements for a prospect with this email.
        for eng in store.list_engagements(status="active"):
            prospects = list(store.list_prospects(eng.id, limit=10_000))
            for p in prospects:
                if (p.email or "").lower() == email and p.status not in ("unsubscribed", "booked"):
                    meeting = ops.book_meeting(
                        engagement_id=eng.id,
                        prospect_id=p.id,
                        scheduled_for=scheduled_for,
                        notes=f"Cal.com booking: {title} (uid={booking_uid})",
                    )
                    booked.append({
                        "engagement_id": eng.id,
                        "prospect_id": p.id,
                        "meeting_id": meeting.id,
                    })
                    logger.info(
                        "Cal.com booking booked: %s → engagement=%s prospect=%s",
                        email, eng.id, p.id,
                    )
                    break  # found for this email, move on

    if not booked:
        # No matching prospect — log and ack (don't 404, to avoid Cal.com retry storms)
        logger.info(
            "Cal.com booking received but no matching prospect found for emails: %s",
            attendee_emails,
        )
        return JSONResponse({
            "ok": True,
            "matched": False,
            "emails_searched": attendee_emails,
            "message": "No matching active prospect found — meeting not recorded",
        })

    return JSONResponse({"ok": True, "matched": True, "booked": booked})


def _handle_cancellation(store, ops, attendee_emails: list[str], booking_uid: str):
    """Find any booked meeting for these emails and mark it cancelled."""
    for email in attendee_emails:
        for eng in store.list_engagements():
            meetings = list(store.list_meetings(eng.id, status="booked", limit=1000))
            for m in meetings:
                prospect = store.get_prospect(m.prospect_id)
                if prospect and (prospect.email or "").lower() == email:
                    # Check note contains this booking uid.
                    if booking_uid and booking_uid not in (m.notes or ""):
                        continue
                    ops.update_meeting_status(m.id, status="cancelled", notes=f"Cancelled via Cal.com webhook (uid={booking_uid})")
                    logger.info("Cal.com cancellation applied to meeting %s", m.id)
    return JSONResponse({"ok": True, "action": "cancelled"})
