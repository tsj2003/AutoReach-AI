"""
M4 — Mailboxes REST API (BYOC OAuth).

GET    /api/mailboxes
POST   /api/mailboxes/connect/start    — platform env creds or BYOC body → Google consent URL
GET    /api/mailboxes/connect/callback — handles OAuth callback, stores mailbox
DELETE /api/mailboxes/{id}             — disconnect

BYOC still works when the body supplies client_id + client_secret. When omitted,
connect/start falls back to GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET from env.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from cockpit.api.deps import get_current_user, get_store
from engine.auth import CurrentUser
from engine.auth.mailbox_models import Mailbox
from engine.adapters.gmail_token_store import (
    authorized_user_info_from_credentials,
    gmail_credentials_are_sendable,
)
from engine.debug_agent import agent_debug
from engine.adapters.google_scopes import (
    GOOGLE_MAILBOX_SCOPES,
    normalize_scopes,
    relax_oauthlib_token_scope,
)

router = APIRouter(prefix="/api/mailboxes", tags=["mailboxes"])
log = logging.getLogger(__name__)

_SCOPES = list(GOOGLE_MAILBOX_SCOPES)

_DEFAULT_LOCAL_REDIRECT = "http://127.0.0.1:8765/api/mailboxes/connect/callback"
_OAUTH_ERROR_REDIRECT = "/app/operations/mailboxes"


def _oauth_error_redirect(error: str) -> RedirectResponse:
    """Send OAuth failures to Mailboxes with a query the UI can explain."""
    reason = (error or "unknown").strip() or "unknown"
    query = urlencode({"error": reason, "oauth_error": reason})
    return RedirectResponse(url=f"{_OAUTH_ERROR_REDIRECT}?{query}", status_code=303)


def _oauth_success_redirect(*, has_refresh_token: bool) -> RedirectResponse:
    query = {"connected": "1"}
    if not has_refresh_token:
        query["warning"] = "missing_refresh_token"
    return RedirectResponse(
        url=f"{_OAUTH_ERROR_REDIRECT}?{urlencode(query)}",
        status_code=303,
    )



_OAUTH_STATE_TTL_SEC = 15 * 60


def encode_mailbox_oauth_state(ctx: dict) -> str:
    """Self-contained OAuth state so callback works on any gunicorn worker.

    Session cookies are signed with a per-process secret when
    AUTOREACH_SESSION_SECRET is unset, so worker A cannot read worker B's
    pending map. Google echoes this state on the callback GET.
    """
    env_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    payload = {
        "client_id": (ctx.get("client_id") or "").strip(),
        "redirect_uri": (ctx.get("redirect_uri") or "").strip(),
        "tenant_id": ctx.get("tenant_id"),
        "user_id": ctx.get("user_id"),
        "exp": int(time.time()) + _OAUTH_STATE_TTL_SEC,
        "nonce": secrets.token_urlsafe(8),
    }
    secret = (ctx.get("client_secret") or "").strip()
    if secret and secret != env_secret:
        payload["client_secret"] = secret
    else:
        payload["client_secret_from_env"] = True
    raw = json.dumps(payload, separators=(",", ":"))
    from engine.security.secrets import encrypt_text

    token = encrypt_text(raw) or raw
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def decode_mailbox_oauth_state(state: str | None) -> dict | None:
    if not state:
        return None
    try:
        token = base64.urlsafe_b64decode(state.encode("ascii")).decode("utf-8")
    except Exception:
        return None
    from engine.security.secrets import decrypt_text

    try:
        raw = decrypt_text(token)
    except Exception:
        return None
    try:
        data = json.loads(raw or "")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if int(data.get("exp") or 0) < int(time.time()):
        return None
    if data.get("client_secret_from_env"):
        data["client_secret"] = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    return data


def _resolve_pending_ctx(request: Request, state: str | None) -> dict | None:
    pending = request.session.get("mailbox_oauth_pending", {})
    ctx = pending.get(state) if state else None
    if ctx:
        return ctx
    return decode_mailbox_oauth_state(state)


def _pending_ctx_error(ctx: dict | None, code: str | None) -> str | None:
    if not ctx or not code:
        return "invalid_or_expired_state"
    if not (ctx.get("client_id") or "").strip() or not (ctx.get("client_secret") or "").strip():
        return "missing_client_secret"
    if not (ctx.get("redirect_uri") or "").strip():
        return "redirect_uri_mismatch"
    return None


def _mailbox_oauth_error_code(exc: BaseException) -> str:
    text = str(exc or "").lower()
    if "scope has changed" in text:
        return "scope_mismatch"
    if "redirect_uri" in text:
        return "redirect_uri_mismatch"
    if "invalid_client" in text or "unauthorized_client" in text:
        return "invalid_client_secret"
    if "invalid_grant" in text:
        return "invalid_or_expired_code"
    if "fernet" in text or "invalidtoken" in text:
        return "credential_encryption_failed"
    if "refresh_token" in text:
        return "missing_refresh_token"
    return "token_exchange_failed"


def _google_flow(*, client_id: str, client_secret: str, redirect_uri: str, state: str | None = None):
    from google_auth_oauthlib.flow import Flow  # type: ignore

    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    kwargs: dict = {"scopes": _SCOPES, "redirect_uri": redirect_uri}
    if state is not None:
        kwargs["state"] = state
    return Flow.from_client_config(config, **kwargs)


class ConnectStart(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None


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
    """Prefer body credentials (BYOC); otherwise platform Google OAuth env vars."""
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
    """Use body redirect, or production public base when localhost/default is omitted."""
    uri = (redirect_uri or "").strip()
    parsed = urlparse(uri) if uri else None
    needs_public = (not uri) or (parsed is not None and _is_localhost(parsed.hostname))
    if needs_public:
        public_base = os.getenv("AUTOREACH_PUBLIC_BASE_URL", "").strip().rstrip("/")
        # Ignore placeholder / commented values that are not real http(s) bases.
        if public_base.startswith(("http://", "https://")):
            return f"{public_base}/api/mailboxes/connect/callback"
    if not uri:
        return _DEFAULT_LOCAL_REDIRECT
    return uri


def _validate_redirect_uri(redirect_uri: str, *, request: Request) -> None:
    parsed = urlparse(redirect_uri)
    if parsed.path != "/api/mailboxes/connect/callback":
        raise HTTPException(400, "redirect_uri must use the mailbox callback path")

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


def _mailbox_to_dict(m: Mailbox) -> dict:
    creds = dict(m.credentials_json or {})
    refresh = str(creds.get("refresh_token") or "").strip()
    token = str(creds.get("token") or creds.get("access_token") or "").strip()
    return {
        "id": m.id, "email_address": m.email_address, "provider": m.provider,
        "display_name": m.display_name, "status": m.status,
        "max_emails_per_day": m.max_emails_per_day,
        "emails_sent_today": m.emails_sent_today,
        "warmup_day": m.warmup_day, "reputation_score": m.reputation_score,
        "last_error": m.last_error,
        "has_refresh_token": bool(refresh),
        "has_access_token": bool(token),
        "token_scope_count": len(creds.get("scopes") or []),
    }


@router.get("")
def list_mailboxes(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    rows = [_mailbox_to_dict(m) for m in store.list_mailboxes(current_user.tenant_id)]
    agent_debug(
        "A",
        "mailboxes.py:list_mailboxes",
        "mailbox token flags",
        {
            "count": len(rows),
            "flags": [
                {
                    "id": row["id"],
                    "status": row["status"],
                    "has_refresh_token": row["has_refresh_token"],
                    "has_access_token": row["has_access_token"],
                    "emails_sent_today": row.get("emails_sent_today"),
                    "has_last_error": bool(row.get("last_error")),
                    "last_error": str(row.get("last_error") or "")[:160],
                }
                for row in rows
            ],
        },
    )
    return rows


@router.post("/connect/start")
def connect_start(
    body: ConnectStart,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    client_id, client_secret = _resolve_oauth_credentials(body.client_id, body.client_secret)
    redirect_uri = _resolve_redirect_uri(body.redirect_uri)
    _validate_redirect_uri(redirect_uri, request=request)

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
        flow = _google_flow(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(500, f"google-auth-oauthlib not installed: {exc}")

    pending_ctx = {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.user_id,
    }
    state = encode_mailbox_oauth_state(pending_ctx)

    # Session is a same-worker hint only. Callback must succeed from `state`.
    pending = request.session.get("mailbox_oauth_pending", {})
    pending[state] = pending_ctx
    request.session["mailbox_oauth_pending"] = pending

    auth_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", state=state,
    )
    agent_debug(
        "B",
        "mailboxes.py:connect_start",
        "oauth start flags",
        {
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": False,
            "state_self_contained": True,
            "has_auth_url": bool(auth_url),
        },
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
        return _oauth_error_redirect(error)
    pending = request.session.get("mailbox_oauth_pending", {})
    ctx = _resolve_pending_ctx(request, state)
    agent_debug(
        "B",
        "mailboxes.py:connect_callback",
        "oauth callback ctx",
        {
            "has_session_ctx": bool(state and pending.get(state)),
            "has_state_ctx": bool(ctx),
            "has_code": bool(code),
        },
    )
    ctx_error = _pending_ctx_error(ctx, code)
    if ctx_error:
        if ctx_error == "missing_client_secret":
            log.error("mailbox OAuth callback missing client credentials")
        return _oauth_error_redirect(ctx_error)

    client_id = (ctx.get("client_id") or "").strip()
    client_secret = (ctx.get("client_secret") or "").strip()
    # Must match the authorize-time redirect_uri stored in session — never re-resolve.
    redirect_uri = (ctx.get("redirect_uri") or "").strip()

    try:
        if _allow_insecure_oauth_transport(redirect_uri):
            os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
        # Google often adds userinfo.profile / previously granted scopes.
        relax_oauthlib_token_scope()
        flow = _google_flow(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            state=state,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials

        email = _discover_email(creds) or "unknown@gmail.com"
        existing = _mailbox_for_email(store, ctx["tenant_id"], email)
        existing_info = dict(existing.credentials_json or {}) if existing else None
        info = authorized_user_info_from_credentials(
            creds,
            fallback_client_id=client_id,
            fallback_client_secret=client_secret,
            existing=existing_info,
        )
        info["scopes"] = normalize_scopes(
            list(getattr(creds, "scopes", None) or info.get("scopes") or _SCOPES)
        )
        sendable, _reason = gmail_credentials_are_sendable(info)
        if not sendable:
            return _oauth_error_redirect("missing_refresh_token")
        now = datetime.now(timezone.utc)
        if existing:
            mailbox = Mailbox(
                id=existing.id,
                tenant_id=existing.tenant_id,
                user_id=existing.user_id or ctx["user_id"],
                provider="gmail",
                email_address=email,
                display_name=existing.display_name or email,
                credentials_json=dict(info),
                oauth_client_id=client_id,
                oauth_client_secret=client_secret,
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
        else:
            mailbox = Mailbox(
                id=_new_id("mbx"),
                tenant_id=ctx["tenant_id"],
                user_id=ctx["user_id"],
                provider="gmail",
                email_address=email,
                display_name=email,
                credentials_json=dict(info),
                oauth_client_id=client_id,
                oauth_client_secret=client_secret,
                status="active",
                created_at=now, updated_at=now,
            )
        store.save_mailbox(mailbox)
        has_refresh = bool(str(info.get("refresh_token") or "").strip())
        has_access = bool(str(info.get("token") or "").strip())
        agent_debug(
            "B",
            "mailboxes.py:connect_callback",
            "oauth callback stored mailbox",
            {
                "mailbox_id": mailbox.id,
                "has_refresh_token": has_refresh,
                "has_access_token": has_access,
                "sendable": sendable,
                "scope_count": len(info.get("scopes") or []),
                "updated_existing": bool(existing),
            },
        )
    except Exception as exc:
        log.exception("mailbox OAuth callback failed")
        return _oauth_error_redirect(_mailbox_oauth_error_code(exc))

    pending.pop(state, None)
    request.session["mailbox_oauth_pending"] = pending
    return _oauth_success_redirect(has_refresh_token=has_refresh)


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


@router.post("/{mailbox_id}/pause")
def pause_mailbox(
    mailbox_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    """Pilot kill switch — router will not send from a paused mailbox."""
    m = store.get_mailbox(mailbox_id)
    if not m or m.tenant_id != current_user.tenant_id:
        raise HTTPException(404, "Mailbox not found")
    if m.status == "revoked":
        raise HTTPException(400, "Mailbox is revoked — reconnect instead")
    store.update_mailbox_status(mailbox_id, status="paused", last_error="paused by operator")
    return {"ok": True, "id": mailbox_id, "status": "paused"}


@router.post("/{mailbox_id}/resume")
def resume_mailbox(
    mailbox_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    m = store.get_mailbox(mailbox_id)
    if not m or m.tenant_id != current_user.tenant_id:
        raise HTTPException(404, "Mailbox not found")
    if m.status == "revoked":
        raise HTTPException(400, "Mailbox is revoked — reconnect instead")
    store.update_mailbox_status(mailbox_id, status="active", last_error=None)
    return {"ok": True, "id": mailbox_id, "status": "active"}



def _mailbox_for_email(store, tenant_id: str, email: str):
    wanted = (email or "").strip().lower()
    if not wanted:
        return None
    for mailbox in store.list_mailboxes(tenant_id):
        if (mailbox.email_address or "").strip().lower() == wanted:
            return mailbox
    return None


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
