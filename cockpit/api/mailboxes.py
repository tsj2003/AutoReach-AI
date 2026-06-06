"""
M4 — Mailboxes REST API (BYOC OAuth).

GET    /api/mailboxes
POST   /api/mailboxes/connect/start    — BYOC: client_id/secret → returns Google consent URL
GET    /api/mailboxes/connect/callback — handles OAuth callback, stores mailbox
DELETE /api/mailboxes/{id}             — disconnect

BYOC = bring your own credentials. The user supplies their own Google Cloud
OAuth client_id + client_secret. We never need Google app verification this way.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from cockpit.api.deps import get_current_user, get_store
from engine.auth import CurrentUser
from engine.auth.mailbox_models import Mailbox

router = APIRouter(prefix="/api/mailboxes", tags=["mailboxes"])

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]


class ConnectStart(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: str = "http://127.0.0.1:8765/api/mailboxes/connect/callback"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _mailbox_to_dict(m: Mailbox) -> dict:
    return {
        "id": m.id, "email_address": m.email_address, "provider": m.provider,
        "display_name": m.display_name, "status": m.status,
        "max_emails_per_day": m.max_emails_per_day,
        "warmup_day": m.warmup_day, "reputation_score": m.reputation_score,
        "last_error": m.last_error,
    }


@router.get("")
def list_mailboxes(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    return [_mailbox_to_dict(m) for m in store.list_mailboxes(current_user.tenant_id)]


@router.post("/connect/start")
def connect_start(
    body: ConnectStart,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    # M5: enforce plan mailbox cap.
    from engine.policies import get_plan_limits
    store = request.app.state.store
    limits = get_plan_limits(current_user.plan)
    existing = store.list_mailboxes(current_user.tenant_id)
    active = [m for m in existing if m.status != "revoked"]
    if len(active) >= limits.max_mailboxes:
        raise HTTPException(
            403,
            f"Plan '{limits.plan}' allows {limits.max_mailboxes} mailbox(es). Upgrade to add more.",
        )

    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise HTTPException(500, f"google-auth-oauthlib not installed: {exc}")

    config = {
        "web": {
            "client_id": body.client_id,
            "client_secret": body.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(config, scopes=_SCOPES, redirect_uri=body.redirect_uri)
    state = secrets.token_urlsafe(24)

    # Stash the BYOC creds + tenant in the session keyed by state.
    pending = request.session.get("mailbox_oauth_pending", {})
    pending[state] = {
        "client_id": body.client_id,
        "client_secret": body.client_secret,
        "redirect_uri": body.redirect_uri,
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.user_id,
    }
    request.session["mailbox_oauth_pending"] = pending

    auth_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent",
        include_granted_scopes="true", state=state,
    )
    return {"authorization_url": auth_url, "state": state}


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
    pending = request.session.get("mailbox_oauth_pending", {})
    ctx = pending.get(state) if state else None
    if not ctx or not code:
        raise HTTPException(400, "Invalid or expired OAuth state")

    from google_auth_oauthlib.flow import Flow  # type: ignore

    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    config = {
        "web": {
            "client_id": ctx["client_id"],
            "client_secret": ctx["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(config, scopes=_SCOPES, redirect_uri=ctx["redirect_uri"], state=state)
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Discover the email address.
    email = _discover_email(creds) or "unknown@gmail.com"

    info = creds.to_authorized_user_info() if hasattr(creds, "to_authorized_user_info") else {}
    now = datetime.now(timezone.utc)
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
        created_at=now, updated_at=now,
    )
    store.save_mailbox(mailbox)

    # Clean up the pending state.
    pending.pop(state, None)
    request.session["mailbox_oauth_pending"] = pending

    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        f"""<html><body style="font-family:monospace;padding:24px;background:#0f1115;color:#e6e9f0">
        <h3>✅ Mailbox connected: {email}</h3>
        <a href="/app/" style="color:#4a8cff">← Back to dashboard</a>
        </body></html>"""
    )


@router.delete("/{mailbox_id}", status_code=204)
def disconnect_mailbox(
    mailbox_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    m = store.get_mailbox(mailbox_id)
    if not m or m.tenant_id != current_user.tenant_id:
        raise HTTPException(404, "Mailbox not found")
    store.update_mailbox_status(mailbox_id, status="revoked", last_error="disconnected by user")


def _discover_email(creds):
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
