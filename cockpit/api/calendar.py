"""
Google Calendar OAuth + booking API (native Attainly / Gojiberry-style).

GET  /api/calendar/status
POST /api/calendar/connect/start
GET  /api/calendar/connect/callback
GET  /api/calendar/freebusy
POST /api/calendar/book

Tokens reuse the mailbox credentials_json blob (encrypted at rest). Connect
requests Gmail + Calendar scopes so one Google account powers Unibox send
and meeting invites.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from cockpit.api.deps import get_current_user, get_ops, get_store
from engine.adapters.gmail_token_store import authorized_user_info_from_credentials
from engine.adapters.google_scopes import GOOGLE_MAILBOX_SCOPES, has_calendar_scopes, normalize_scopes, relax_oauthlib_token_scope
from engine.auth import CurrentUser
from engine.auth.mailbox_models import Mailbox
from engine.services.google_calendar import (
    CalendarApiError,
    CalendarNotConnected,
    GoogleCalendarService,
)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

_DEFAULT_LOCAL_REDIRECT = "http://127.0.0.1:8765/api/calendar/connect/callback"


class ConnectStart(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None
    mailbox_id: str | None = None


class BookRequest(BaseModel):
    prospect_email: str
    prospect_name: str | None = None
    start_iso: str
    end_iso: str
    title: str | None = None
    description: str | None = None
    timezone: str | None = "UTC"
    create_meet: bool = True
    mailbox_id: str | None = None
    campaign_id: str | None = None
    prospect_id: str | None = None
    reply_id: str | None = None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _production_mode() -> bool:
    return os.getenv("AUTOREACH_ENABLE_CONSOLE", "1").strip().lower() in {
        "0", "false", "no", "off",
    }


def _is_localhost(hostname: str | None) -> bool:
    return (hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}


def _resolve_oauth_credentials(
    client_id: str | None,
    client_secret: str | None,
) -> tuple[str, str]:
    resolved_id = (client_id or "").strip() or os.getenv("GOOGLE_CLIENT_ID", "").strip()
    resolved_secret = (
        (client_secret or "").strip() or os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    )
    if not resolved_id or not resolved_secret:
        raise HTTPException(
            400,
            "client_id and client_secret are required, or set GOOGLE_CLIENT_ID "
            "and GOOGLE_CLIENT_SECRET on the server.",
        )
    return resolved_id, resolved_secret


def _resolve_redirect_uri(redirect_uri: str | None) -> str:
    uri = (redirect_uri or "").strip()
    parsed = urlparse(uri) if uri else None
    needs_public = (not uri) or (parsed is not None and _is_localhost(parsed.hostname))
    if needs_public:
        public_base = os.getenv("AUTOREACH_PUBLIC_BASE_URL", "").strip().rstrip("/")
        # Ignore placeholder / commented values that are not real http(s) bases.
        if public_base.startswith(("http://", "https://")):
            return f"{public_base}/api/calendar/connect/callback"
    if not uri:
        return _DEFAULT_LOCAL_REDIRECT
    return uri


def _validate_redirect_uri(redirect_uri: str, *, request: Request) -> None:
    parsed = urlparse(redirect_uri)
    if parsed.path != "/api/calendar/connect/callback":
        raise HTTPException(400, "redirect_uri must use the calendar callback path")

    if not _production_mode():
        if parsed.scheme == "https":
            return
        if parsed.scheme == "http" and _is_localhost(parsed.hostname):
            return
        raise HTTPException(400, "redirect_uri must be HTTPS or local HTTP")

    expected_host = request.url.hostname
    public_base = os.getenv("AUTOREACH_PUBLIC_BASE_URL", "").strip()
    if public_base:
        expected_host = urlparse(public_base).hostname or expected_host

    if parsed.scheme != "https":
        raise HTTPException(400, "redirect_uri must be HTTPS in production")
    if parsed.hostname != expected_host:
        raise HTTPException(400, "redirect_uri host must match this deployment")


def _allow_insecure_oauth_transport(redirect_uri: str) -> bool:
    parsed = urlparse(redirect_uri)
    return parsed.scheme == "http" and _is_localhost(parsed.hostname)


def _discover_email(creds) -> str | None:
    try:
        import json as _json
        import urllib.request as _req

        req = _req.Request(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
        )
        with _req.urlopen(req, timeout=5) as resp:
            return _json.loads(resp.read()).get("email")
    except Exception:
        return None


@router.get("/status")
def calendar_status(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    return GoogleCalendarService(store=store, tenant_id=current_user.tenant_id).status()


@router.post("/connect/start")
def connect_start(
    body: ConnectStart,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    """Begin Calendar (+ Gmail) re-consent; tokens land on the mailbox row."""
    client_id, client_secret = _resolve_oauth_credentials(body.client_id, body.client_secret)
    redirect_uri = _resolve_redirect_uri(body.redirect_uri)
    _validate_redirect_uri(redirect_uri, request=request)

    target_mailbox_id = (body.mailbox_id or "").strip() or None
    if target_mailbox_id:
        m = store.get_mailbox(target_mailbox_id)
        if not m or m.tenant_id != current_user.tenant_id:
            raise HTTPException(404, "Mailbox not found")
    else:
        # Prefer upgrading an existing Gmail mailbox.
        active = [m for m in store.list_mailboxes(current_user.tenant_id) if m.status != "revoked"]
        if active:
            target_mailbox_id = active[0].id

    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise HTTPException(500, f"google-auth-oauthlib not installed: {exc}")

    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(
        config, scopes=GOOGLE_MAILBOX_SCOPES, redirect_uri=redirect_uri
    )
    state = secrets.token_urlsafe(24)
    pending = request.session.get("calendar_oauth_pending", {})
    pending[state] = {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.user_id,
        "mailbox_id": target_mailbox_id,
    }
    request.session["calendar_oauth_pending"] = pending

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        state=state,
    )
    return {
        "authorization_url": auth_url,
        "state": state,
        "scopes": list(GOOGLE_MAILBOX_SCOPES),
        "mailbox_id": target_mailbox_id,
    }


@router.get("/connect/callback")
def connect_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    store=Depends(get_store),
):
    if error:
        raise HTTPException(400, f"OAuth denied: {error}")
    pending = request.session.get("calendar_oauth_pending", {})
    ctx = pending.get(state) if state else None
    if not ctx or not code:
        raise HTTPException(400, "Invalid or expired OAuth state")

    from google_auth_oauthlib.flow import Flow  # type: ignore

    if _allow_insecure_oauth_transport(ctx["redirect_uri"]):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    config = {
        "web": {
            "client_id": ctx["client_id"],
            "client_secret": ctx["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    # include_granted_scopes can return a superset; accept any scopes from Google.
    flow = Flow.from_client_config(
        config,
        scopes=GOOGLE_MAILBOX_SCOPES,
        redirect_uri=ctx["redirect_uri"],
        state=state,
    )
    # google-auth-oauthlib may raise ScopeChangeError when scopes expand; allow it.
    relax_oauthlib_token_scope()
    flow.fetch_token(code=code)
    creds = flow.credentials

    email = _discover_email(creds) or "unknown@gmail.com"
    mailbox_id = ctx.get("mailbox_id")
    existing_for_merge = store.get_mailbox(mailbox_id) if mailbox_id else None
    existing_info = dict(existing_for_merge.credentials_json or {}) if existing_for_merge else None
    info = authorized_user_info_from_credentials(
        creds,
        fallback_client_id=ctx["client_id"],
        fallback_client_secret=ctx["client_secret"],
        existing=existing_info,
    )
    info["scopes"] = normalize_scopes(
        list(getattr(creds, "scopes", None) or info.get("scopes") or GOOGLE_MAILBOX_SCOPES)
    )
    if not has_calendar_scopes(info.get("scopes")):
        # Persist anyway but surface that Calendar was not granted.
        pass

    now = datetime.now(timezone.utc)
    existing = existing_for_merge if existing_for_merge and existing_for_merge.tenant_id == ctx["tenant_id"] else None
    if existing and existing.tenant_id == ctx["tenant_id"]:
        store.update_mailbox_credentials(existing.id, credentials_json=dict(info))
        # Refresh oauth client fields if provided.
        store.save_mailbox(
            Mailbox(
                id=existing.id,
                tenant_id=existing.tenant_id,
                user_id=existing.user_id or ctx["user_id"],
                provider=existing.provider,
                email_address=email or existing.email_address,
                display_name=existing.display_name or email,
                credentials_json=dict(info),
                oauth_client_id=ctx["client_id"],
                oauth_client_secret=ctx["client_secret"],
                max_emails_per_day=existing.max_emails_per_day,
                emails_sent_today=existing.emails_sent_today,
                last_send_reset=existing.last_send_reset,
                warmup_day=existing.warmup_day,
                status="active",
                reputation_score=existing.reputation_score,
                last_error=None,
                created_at=existing.created_at,
                updated_at=now,
            )
        )
        connected_email = email or existing.email_address
    else:
        mailbox = Mailbox(
            id=_new_id("mbx"),
            tenant_id=ctx["tenant_id"],
            user_id=ctx["user_id"],
            provider="gmail",
            email_address=email,
            display_name=email,
            credentials_json=dict(info),
            oauth_client_id=ctx["client_id"],
            oauth_client_secret=ctx["client_secret"],
            status="active",
            created_at=now,
            updated_at=now,
        )
        store.save_mailbox(mailbox)
        connected_email = email

    pending.pop(state, None)
    request.session["calendar_oauth_pending"] = pending

    cal_ok = has_calendar_scopes(info.get("scopes"))
    return HTMLResponse(
        f"""<html><body style="font-family:monospace;padding:24px;background:#0f1115;color:#e6e9f0">
        <h3>{"✅" if cal_ok else "⚠"} Google Calendar {"connected" if cal_ok else "connected without Calendar scope"}: {connected_email}</h3>
        <p>Scopes: {", ".join(info.get("scopes") or [])}</p>
        <p>Enable the Google Calendar API in Cloud Console and re-consent if booking fails.</p>
        <a href="/app/integrations" style="color:#FA651E">← Back to Attainly Integrations</a>
        </body></html>"""
    )


@router.get("/freebusy")
def freebusy(
    days: int = Query(default=7, ge=1, le=21),
    slot_minutes: int = Query(default=30, ge=15, le=120),
    max_slots: int = Query(default=8, ge=1, le=24),
    timezone: str = Query(default="America/New_York"),
    mailbox_id: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    svc = GoogleCalendarService(
        store=store, tenant_id=current_user.tenant_id, mailbox_id=mailbox_id
    )
    try:
        slots = svc.list_free_slots(
            days=days,
            slot_minutes=slot_minutes,
            max_slots=max_slots,
            timezone_name=timezone,
        )
    except CalendarNotConnected as exc:
        raise HTTPException(409, str(exc)) from exc
    except CalendarApiError as exc:
        raise HTTPException(502, str(exc)) from exc
    status = svc.status()
    return {
        "connected": True,
        "email": status.get("email"),
        "timezone": timezone,
        "slot_minutes": slot_minutes,
        "slots": [s.to_dict() for s in slots],
    }


@router.post("/book")
def book(
    body: BookRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    svc = GoogleCalendarService(
        store=store,
        tenant_id=current_user.tenant_id,
        mailbox_id=body.mailbox_id,
    )
    try:
        booked = svc.book_event(
            prospect_email=body.prospect_email,
            prospect_name=body.prospect_name or "",
            start_iso=body.start_iso,
            end_iso=body.end_iso,
            title=body.title or "",
            description=body.description or "",
            timezone_name=body.timezone or "UTC",
            create_meet=body.create_meet,
        )
    except CalendarNotConnected as exc:
        raise HTTPException(409, str(exc)) from exc
    except CalendarApiError as exc:
        raise HTTPException(502, str(exc)) from exc

    meeting_id = None
    if body.campaign_id and body.prospect_id:
        if not store.get_engagement(body.campaign_id, tenant_id=current_user.tenant_id):
            raise HTTPException(404, "Campaign not found")
        start = datetime.fromisoformat(
            body.start_iso.replace("Z", "+00:00")
            if body.start_iso.endswith("Z")
            else body.start_iso
        )
        notes = (
            f"gcal_event_id={booked.event_id}; meet_link={booked.meet_link}; "
            f"html_link={booked.html_link}"
        )
        meeting = ops.book_meeting(
            engagement_id=body.campaign_id,
            prospect_id=body.prospect_id,
            scheduled_for=start,
            reply_id=body.reply_id,
            notes=notes,
        )
        meeting_id = meeting.id
        _persist_meeting_meta(
            store,
            prospect_id=body.prospect_id,
            event=booked,
        )

    payload = booked.to_dict()
    return {
        "ok": True,
        "meeting_id": meeting_id,
        "gcal_event_id": payload.get("event_id"),
        "gcal_html_link": payload.get("html_link"),
        **payload,
    }


def _persist_meeting_meta(store, *, prospect_id: str, event) -> None:
    from engine.core.types import Prospect

    p = store.get_prospect(prospect_id)
    if p is None:
        return
    raw = dict(p.raw or {})
    raw["meeting_booked_at"] = datetime.now(timezone.utc).isoformat()
    raw["gcal_event_id"] = event.event_id
    raw["meet_link"] = event.meet_link
    raw["gcal_html_link"] = event.html_link
    store.save_prospect(
        Prospect(
            id=p.id,
            engagement_id=p.engagement_id,
            email=p.email,
            full_name=p.full_name,
            company=p.company,
            title=p.title,
            raw=raw,
            research=p.research,
            status="booked",
            created_at=p.created_at,
        )
    )
