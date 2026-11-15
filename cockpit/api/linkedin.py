"""LinkedIn Voyager Seat Management, Post Engager Scraping & Unibox Sync API (`/api/linkedin/*`).

Provides:
- `POST /api/linkedin/connect`: Stores Fernet-encrypted `li_at` and `jsession_id` cookies + optional `proxy_url`
  and validates the session via `GET https://www.linkedin.com/voyager/api/me`.
- `GET /api/linkedin/seats`: Lists connected LinkedIn Voyager seats, daily limits, and status.
- `DELETE /api/linkedin/seats/{seat_id}`: Disconnects a LinkedIn seat.
- `POST /api/linkedin/scrape-post-engagers`: Scrapes likers & commenters from a LinkedIn post or competitor page URL.
- `POST /api/linkedin/sync-inbox`: Syncs Voyager DM threads (`linkedinMessageBackendUrn`) into Unibox 2.0 (`ReplyStore`).
- `POST /api/linkedin/execute-action`: Executes a Voyager action (`visitProfile`, `likePosts`, `invitation`, `invitationNote`, `message`).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
import io
import zipfile
from pathlib import Path

from cockpit.api.deps import get_current_user, get_store
from engine.dispatch.linkedin_provider import LinkedInProvider, strip_jsessionid_quotes
from engine.integrations.linkedin_oauth import (
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_userinfo,
    linkedin_client_id,
    linkedin_client_secret,
    linkedin_oauth_configured,
    normalize_profile,
)
from engine.security.secrets import decrypt_text, encrypt_text
import base64
import os
from cryptography.fernet import Fernet

_OAUTH_STATE_TTL_SEC = 900


def _fallback_fernet() -> Fernet:
    seed = os.getenv("AUTOREACH_SECRET_KEY") or os.getenv("AUTOREACH_JWT_SECRET") or "autoreach-linkedin-voyager-fernet-key"
    key = base64.urlsafe_b64encode(hashlib.sha256(seed.encode("utf-8")).digest())
    return Fernet(key)


def _encrypt_cookie(plain: str) -> str:
    if not plain:
        return ""
    res = encrypt_text(plain) or ""
    if res.startswith("enc:v1:"):
        return res
    token = _fallback_fernet().encrypt(plain.encode("utf-8")).decode("utf-8")
    return f"enc:v1:{token}"


def _decrypt_cookie(value: str) -> str:
    if not value:
        return ""
    try:
        res = decrypt_text(value)
        if res and not res.startswith("enc:v1:"):
            return res
    except Exception:
        res = ""
    if value.startswith("enc:v1:"):
        raw_tok = value[len("enc:v1:"):]
        try:
            return _fallback_fernet().decrypt(raw_tok.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""
    return res or ""


router = APIRouter(prefix="/api/linkedin", tags=["linkedin-voyager"])


def _ensure_linkedin_seats_table(store: Any) -> None:
    engine = store._holder.engine
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS linkedin_seats (
                    id VARCHAR(64) PRIMARY KEY,
                    tenant_id VARCHAR(64) NOT NULL,
                    user_id VARCHAR(64) NOT NULL,
                    account_name VARCHAR(255) NOT NULL,
                    public_identifier VARCHAR(255) NOT NULL,
                    member_urn VARCHAR(255) NOT NULL,
                    headline VARCHAR(512) NOT NULL DEFAULT '',
                    li_at_encrypted TEXT NOT NULL,
                    jsession_id_encrypted TEXT NOT NULL,
                    proxy_url VARCHAR(512),
                    daily_connection_limit INTEGER NOT NULL DEFAULT 25,
                    daily_message_limit INTEGER NOT NULL DEFAULT 50,
                    daily_profile_views_limit INTEGER NOT NULL DEFAULT 80,
                    connections_sent_today INTEGER NOT NULL DEFAULT 0,
                    messages_sent_today INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(64) NOT NULL DEFAULT 'connected',
                    mode VARCHAR(64) NOT NULL DEFAULT 'live_voyager',
                    created_at VARCHAR(64) NOT NULL,
                    updated_at VARCHAR(64) NOT NULL
                )
                """
            )
        )
        # Official OAuth / OIDC columns (additive; safe on SQLite + Postgres).
        for ddl in (
            "ALTER TABLE linkedin_seats ADD COLUMN email VARCHAR(255)",
            "ALTER TABLE linkedin_seats ADD COLUMN access_token_encrypted TEXT",
            "ALTER TABLE linkedin_seats ADD COLUMN refresh_token_encrypted TEXT",
            "ALTER TABLE linkedin_seats ADD COLUMN token_expires_at VARCHAR(64)",
            "ALTER TABLE linkedin_seats ADD COLUMN oauth_scopes VARCHAR(512)",
        ):
            try:
                conn.execute(text(ddl))
            except Exception:
                pass  # column already exists


def _get_tenant_id(user: Any) -> str:
    return getattr(user, "tenant_id", None) or getattr(user, "id", "tenant_default")


def _get_user_id(user: Any) -> str:
    return getattr(user, "user_id", None) or getattr(user, "id", "user_default")



def _ensure_pairing_table(store: Any) -> None:
    engine = store._holder.engine
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS linkedin_pairing_tokens (
                    token VARCHAR(64) PRIMARY KEY,
                    tenant_id VARCHAR(64) NOT NULL,
                    user_id VARCHAR(64) NOT NULL,
                    expires_at VARCHAR(64) NOT NULL,
                    used_at VARCHAR(64),
                    created_at VARCHAR(64) NOT NULL
                )
                """
            )
        )


def _extension_root() -> Path:
    return Path(__file__).resolve().parents[2] / "chrome-extension"


def _build_extension_zip() -> bytes:
    root = _extension_root()
    if not root.is_dir():
        raise FileNotFoundError("chrome-extension source is missing from this image")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.name in {".DS_Store"} or "__pycache__" in path.parts:
                continue
            zf.write(path, Path("attainly-linkedin-helper") / path.relative_to(root))
    return buf.getvalue()


def _persist_linkedin_seat(
    *,
    store: Any,
    tenant_id: str,
    user_id: str,
    li_at_clean: str,
    jsession_clean: str,
    proxy_url: Optional[str],
    account_name: Optional[str],
    daily_connection_limit: int = 25,
    daily_message_limit: int = 50,
    daily_profile_views_limit: int = 80,
) -> Dict[str, Any]:
    _ensure_linkedin_seats_table(store)
    provider = LinkedInProvider(
        li_at=li_at_clean,
        jsession_id=jsession_clean,
        proxy_url=proxy_url,
    )
    session_info = provider.validate_session_sync()

    li_at_encrypted = _encrypt_cookie(li_at_clean)
    jsession_encrypted = _encrypt_cookie(jsession_clean)

    public_id = session_info.get("public_id") or "linkedin-operator"
    seat_id = f"liseat_{hashlib.sha1(f'{tenant_id}:{public_id}'.encode('utf-8')).hexdigest()[:12]}"
    resolved_name = (account_name or "").strip() or session_info.get("full_name") or "LinkedIn Operator"
    member_urn = session_info.get("member_urn") or f"urn:li:fsd_profile:ACoAA_{public_id}"
    headline = session_info.get("headline") or "B2B Growth Operator"
    mode = session_info.get("mode", provider.mode)
    status_str = "connected" if li_at_clean else "dry_run_no_cookie"
    now = datetime.now(timezone.utc).isoformat()

    engine = store._holder.engine
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM linkedin_seats WHERE id = :id"),
            {"id": seat_id},
        ).first()
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE linkedin_seats
                    SET account_name = :account_name,
                        public_identifier = :public_id,
                        member_urn = :member_urn,
                        headline = :headline,
                        li_at_encrypted = :li_enc,
                        jsession_id_encrypted = :js_enc,
                        proxy_url = :proxy_url,
                        daily_connection_limit = :conn_limit,
                        daily_message_limit = :msg_limit,
                        daily_profile_views_limit = :view_limit,
                        status = :status,
                        mode = :mode,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": seat_id,
                    "account_name": resolved_name,
                    "public_id": public_id,
                    "member_urn": member_urn,
                    "headline": headline,
                    "li_enc": li_at_encrypted,
                    "js_enc": jsession_encrypted,
                    "proxy_url": proxy_url,
                    "conn_limit": daily_connection_limit,
                    "msg_limit": daily_message_limit,
                    "view_limit": daily_profile_views_limit,
                    "status": status_str,
                    "mode": mode,
                    "updated_at": now,
                },
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO linkedin_seats (
                        id, tenant_id, user_id, account_name, public_identifier, member_urn,
                        headline, li_at_encrypted, jsession_id_encrypted, proxy_url,
                        daily_connection_limit, daily_message_limit, daily_profile_views_limit,
                        connections_sent_today, messages_sent_today, status, mode, created_at, updated_at
                    ) VALUES (
                        :id, :tenant_id, :user_id, :account_name, :public_id, :member_urn,
                        :headline, :li_enc, :js_enc, :proxy_url,
                        :conn_limit, :msg_limit, :view_limit,
                        0, 0, :status, :mode, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": seat_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "account_name": resolved_name,
                    "public_id": public_id,
                    "member_urn": member_urn,
                    "headline": headline,
                    "li_enc": li_at_encrypted,
                    "js_enc": jsession_encrypted,
                    "proxy_url": proxy_url,
                    "conn_limit": daily_connection_limit,
                    "msg_limit": daily_message_limit,
                    "view_limit": daily_profile_views_limit,
                    "status": status_str,
                    "mode": mode,
                    "created_at": now,
                    "updated_at": now,
                },
            )

    return {
        "ok": True,
        "seat_id": seat_id,
        "has_encrypted_cookie": bool(li_at_encrypted.startswith("enc:v1:")),
        "seat": {
            "id": seat_id,
            "tenant_id": tenant_id,
            "account_name": resolved_name,
            "public_identifier": public_id,
            "member_urn": member_urn,
            "headline": headline,
            "proxy_url": proxy_url,
            "encrypted_with_fernet": bool(li_at_encrypted.startswith("enc:v1:")),
            "daily_limits": {
                "connections": daily_connection_limit,
                "messages": daily_message_limit,
                "profile_views": daily_profile_views_limit,
            },
            "status": status_str,
            "mode": mode,
            "updated_at": now,
        },
        "voyager_session": session_info,
    }


def get_active_linkedin_provider(store: Any, tenant_id: str, seat_id: Optional[str] = None) -> LinkedInProvider:
    """Load the tenant's active LinkedIn seat, decrypt `li_at` + `jsession_id`, and return `LinkedInProvider`."""
    _ensure_linkedin_seats_table(store)
    engine = store._holder.engine
    with engine.begin() as conn:
        if seat_id:
            row = conn.execute(
                text("SELECT * FROM linkedin_seats WHERE id = :id AND tenant_id = :tid"),
                {"id": seat_id, "tid": tenant_id},
            ).mappings().first()
        else:
            row = conn.execute(
                text("SELECT * FROM linkedin_seats WHERE tenant_id = :tid ORDER BY updated_at DESC LIMIT 1"),
                {"tid": tenant_id},
            ).mappings().first()

    if not row:
        return LinkedInProvider()

    li_at_plain = _decrypt_cookie(row["li_at_encrypted"])
    jsession_plain = _decrypt_cookie(row["jsession_id_encrypted"])
    return LinkedInProvider(
        li_at=li_at_plain,
        jsession_id=jsession_plain,
        proxy_url=row.get("proxy_url"),
    )


class ConnectLinkedInSeatRequest(BaseModel):
    li_at: str = Field(default="", description="LinkedIn `li_at` session cookie")
    jsession_id: str = Field(default="", description="LinkedIn `JSESSIONID` CSRF cookie")
    proxy_url: Optional[str] = Field(default=None, description="Optional HTTP/SOCKS5 residential proxy URL")
    account_name: Optional[str] = Field(default=None, description="Optional display name override")
    seat_name: Optional[str] = Field(default=None, description="Alias for account_name")
    daily_connection_limit: int = Field(default=25, ge=1, le=100)
    daily_message_limit: int = Field(default=50, ge=1, le=200)
    daily_profile_views_limit: int = Field(default=80, ge=1, le=250)



class PairingTokenResponse(BaseModel):
    ok: bool = True
    token: str
    expires_at: str
    ttl_seconds: int = 900
    download_url: str = "/api/linkedin/chrome-extension.zip"
    connect_path: str = "/api/linkedin/connect-by-token"


class ConnectByTokenRequest(BaseModel):
    token: str = Field(..., min_length=6, max_length=80)
    li_at: str = Field(..., min_length=8)
    jsession_id: str = Field(default="")
    proxy_url: Optional[str] = None
    account_name: Optional[str] = None

class ScrapePostEngagersRequest(BaseModel):
    post_url: str = Field(..., description="LinkedIn post URL, activity URN, or competitor page URL")
    signal_type: str = Field(
        default="POST_WITH_RECENT_ACTIVITY",
        description="One of PROFILE_ENGAGEMENT, COMPANY_ENGAGEMENT, POST_WITH_RECENT_ACTIVITY, COMPETITOR_PAGE_URL",
    )
    count: int = Field(default=50, ge=1, le=100)
    campaign_id: Optional[str] = Field(default=None, description="Optional campaign/engagement ID to enroll scraped leads")
    seat_id: Optional[str] = None


class SyncLinkedInInboxRequest(BaseModel):
    campaign_id: Optional[str] = None
    seat_id: Optional[str] = None
    limit: int = Field(default=25, ge=1, le=50)


class ExecuteVoyagerActionRequest(BaseModel):
    action: Optional[str] = Field(default=None, description="visitProfile | likePosts | invitation | invitationNote | message")
    step_type: Optional[str] = Field(default=None, description="Alias for action")
    profile_url: str = Field(..., description="Target LinkedIn profile URL or URN")
    message: Optional[str] = None
    splitLinkedinMessagesIntoConversation: bool = False
    split_into_conversation: bool = False
    count: int = 2
    seat_id: Optional[str] = None


@router.post("/connect")
def connect_linkedin_seat(
    req: ConnectLinkedInSeatRequest,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Encrypt and store `li_at` + `JSESSIONID` cookies with Fernet and validate via `/voyager/api/me`."""
    _ensure_linkedin_seats_table(store)
    tenant_id = _get_tenant_id(user)
    user_id = _get_user_id(user)

    li_at_clean = req.li_at.strip().strip('"').strip("'")
    jsession_clean = strip_jsessionid_quotes(req.jsession_id)
    if li_at_clean and not jsession_clean:
        digest = hashlib.sha1(li_at_clean.encode("utf-8")).hexdigest()[:16]
        jsession_clean = f"ajax:{int(digest, 16) % (10**19)}"

    return _persist_linkedin_seat(
        store=store,
        tenant_id=tenant_id,
        user_id=user_id,
        li_at_clean=li_at_clean,
        jsession_clean=jsession_clean,
        proxy_url=req.proxy_url,
        account_name=req.account_name or req.seat_name,
        daily_connection_limit=req.daily_connection_limit,
        daily_message_limit=req.daily_message_limit,
        daily_profile_views_limit=req.daily_profile_views_limit,
    )



@router.get("/seats")
def list_linkedin_seats(
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """List connected LinkedIn Voyager seats, daily limits, encryption status, and protocol health."""
    _ensure_linkedin_seats_table(store)
    tenant_id = _get_tenant_id(user)
    engine = store._holder.engine
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT * FROM linkedin_seats WHERE tenant_id = :tid ORDER BY updated_at DESC"),
            {"tid": tenant_id},
        ).mappings().all()

    seats: List[Dict[str, Any]] = []
    for r in rows:
        li_enc = str(r["li_at_encrypted"] or "")
        mode = str(r["mode"] or "")
        has_oauth = bool(r.get("access_token_encrypted"))
        has_cookie = bool(li_enc)
        if has_oauth and mode in {"openid", "oauth", "oauth_openid"}:
            auth_method = "linkedin_oauth"
        elif has_cookie:
            auth_method = "legacy_cookie"
        else:
            auth_method = "unknown"
        seats.append(
            {
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "account_name": r["account_name"],
                "public_identifier": r["public_identifier"],
                "member_urn": r["member_urn"],
                "headline": r["headline"],
                "email": r.get("email") or "",
                "proxy_url": r["proxy_url"],
                "encrypted_with_fernet": li_enc.startswith("enc:v1:") or str(r.get("access_token_encrypted") or "").startswith("enc:v1:"),
                "has_cookie": has_cookie,
                "has_oauth_token": has_oauth,
                "auth_method": auth_method,
                "can_auto_message": has_cookie,  # official OAuth cannot send DMs/connects
                "daily_limits": {
                    "connections": r["daily_connection_limit"],
                    "messages": r["daily_message_limit"],
                    "profile_views": r["daily_profile_views_limit"],
                },
                "usage_today": {
                    "connections_sent": r["connections_sent_today"],
                    "messages_sent": r["messages_sent_today"],
                },
                "status": r["status"],
                "mode": mode,
                "oauth_scopes": r.get("oauth_scopes") or "",
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
        )

    return {
        "ok": True,
        "count": len(seats),
        "seats": seats,
        "oauth_configured": linkedin_oauth_configured(),
        "preferred_auth": "linkedin_oauth",
        "protocol_version": "2.0.0",
        "supported_actions": [
            "visitProfile",
            "likePosts",
            "invitation",
            "invitationNote",
            "message",
            "sync_conversations",
            "fetch_post_engagers",
        ],
        "capability_note": (
            "Sign In with LinkedIn (OIDC) verifies identity. "
            "LinkedIn does not offer self-serve OAuth for cold DMs or connection requests; "
            "campaign LinkedIn steps fall back to email unless a legacy Voyager cookie seat exists."
        ),
    }


@router.delete("/seats/{seat_id}")
def delete_linkedin_seat(
    seat_id: str,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    _ensure_linkedin_seats_table(store)
    tenant_id = _get_tenant_id(user)
    engine = store._holder.engine
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM linkedin_seats WHERE id = :id AND tenant_id = :tid"),
            {"id": seat_id, "tid": tenant_id},
        )
    return {"ok": True, "deleted_seat_id": seat_id}


@router.post("/scrape-post-engagers")
def scrape_post_engagers(
    req: ScrapePostEngagersRequest,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Scrape LinkedIn post likers and commenters via `/voyager/api/socialActions/{urn}/likes` & `/comments`."""
    tenant_id = _get_tenant_id(user)
    provider = get_active_linkedin_provider(store, tenant_id, seat_id=req.seat_id)
    result = provider.fetch_post_engagers_sync(
        req.post_url,
        signal_type=req.signal_type,
        count=req.count,
        store=store,
        engagement_id=req.campaign_id,
        tenant_id=tenant_id,
    )
    result.setdefault('persisted_signals', result.get('persisted_signals_count', result.get('count', 0)))
    return result


@router.post("/sync-inbox")
def sync_linkedin_inbox(
    req: SyncLinkedInInboxRequest,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Sync LinkedIn Voyager DM conversations (`LEGACY_INBOX`) into `ReplyStore` / Unibox 2.0."""
    tenant_id = _get_tenant_id(user)
    provider = get_active_linkedin_provider(store, tenant_id, seat_id=req.seat_id)
    result = provider.sync_conversations_sync(
        store=store,
        engagement_id=req.campaign_id,
        tenant_id=tenant_id,
        limit=req.limit,
    )
    return result


@router.post("/execute-action")
def execute_voyager_action(
    req: ExecuteVoyagerActionRequest,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Execute a live or dry-run LinkedIn Voyager step (`visitProfile`, `likePosts`, `invitation`, `invitationNote`, `message`)."""
    tenant_id = _get_tenant_id(user)
    provider = get_active_linkedin_provider(store, tenant_id, seat_id=req.seat_id)
    action = (req.action or req.step_type or "message").strip()

    if action == "visitProfile":
        return provider.visit_profile_sync(req.profile_url)
    if action == "likePosts":
        return provider.like_posts_sync(req.profile_url, count=req.count)
    if action in ("invitation", "invitationNote"):
        return provider.send_invitation_sync(
            req.profile_url,
            custom_message=req.message if action == "invitationNote" else None,
        )
    if action == "message":
        return provider.send_message_sync(
            req.profile_url,
            req.message or "Hi! Wanted to connect.",
            split_into_conversation=bool(req.splitLinkedinMessagesIntoConversation or req.split_into_conversation),
        )
    raise HTTPException(status_code=400, detail=f"Unsupported LinkedIn Voyager action: {action}")


@router.get("/chrome-extension.zip", include_in_schema=True)
def download_chrome_extension() -> Response:
    """Serve the unpacked Chrome MV3 helper as a zip. No password login; cookie pairing only."""
    try:
        payload = _build_extension_zip()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=attainly-linkedin-helper.zip",
            "Cache-Control": "no-store",
        },
    )


def _mint_pairing_token(store: Any, tenant_id: str, user_id: str) -> Dict[str, Any]:
    _ensure_pairing_table(store)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=15)
    token = "ATN-" + secrets.token_hex(3).upper() + "-" + secrets.token_hex(2).upper()
    engine = store._holder.engine
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO linkedin_pairing_tokens (token, tenant_id, user_id, expires_at, used_at, created_at)
                VALUES (:token, :tenant_id, :user_id, :expires_at, NULL, :created_at)
                """
            ),
            {
                "token": token,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "expires_at": expires.isoformat(),
                "created_at": now.isoformat(),
            },
        )
    return {
        "ok": True,
        "token": token,
        "expires_at": expires.isoformat(),
        "ttl_seconds": 900,
        "download_url": "/api/linkedin/chrome-extension.zip",
        "connect_path": "/api/linkedin/connect-by-token",
        "install": [
            "Download attainly-linkedin-helper.zip",
            "Unzip, then Chrome → chrome://extensions → Developer mode → Load unpacked",
            "Open LinkedIn in this Chrome profile",
            "Paste the pairing token into the extension popup and click Connect",
        ],
    }


@router.post("/pairing-token")
def create_pairing_token(
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Mint a 15-minute one-time token the Chrome extension uses instead of a password."""
    return _mint_pairing_token(store, _get_tenant_id(user), _get_user_id(user))


@router.get("/pairing-token")
def get_pairing_token(
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    return _mint_pairing_token(store, _get_tenant_id(user), _get_user_id(user))


@router.post("/connect-by-token")
def connect_linkedin_by_token(
    req: ConnectByTokenRequest,
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Extension callback: pairing token + LinkedIn cookies. JWT is not required."""
    _ensure_pairing_table(store)
    token = req.token.strip().upper()
    engine = store._holder.engine
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT * FROM linkedin_pairing_tokens WHERE upper(token) = :token"),
            {"token": token},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=401, detail="Unknown pairing token")
        row = dict(row)
        if row.get("used_at"):
            raise HTTPException(status_code=409, detail="Pairing token already used")
        expires_at = datetime.fromisoformat(str(row["expires_at"]))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Pairing token expired")

    li_at_clean = req.li_at.strip().strip('"').strip("'")
    jsession_clean = strip_jsessionid_quotes(req.jsession_id)
    if li_at_clean and not jsession_clean:
        digest = hashlib.sha1(li_at_clean.encode("utf-8")).hexdigest()[:16]
        jsession_clean = f"ajax:{int(digest, 16) % (10**19)}"
    if not li_at_clean:
        raise HTTPException(status_code=400, detail="li_at cookie is required")

    persisted = _persist_linkedin_seat(
        store=store,
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        li_at_clean=li_at_clean,
        jsession_clean=jsession_clean,
        proxy_url=req.proxy_url,
        account_name=req.account_name,
    )
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE linkedin_pairing_tokens SET used_at = :used WHERE token = :token"),
            {"used": datetime.now(timezone.utc).isoformat(), "token": row["token"]},
        )
    persisted["paired_with"] = "chrome-extension"
    return persisted


# ─── Official LinkedIn Sign-In (OpenID Connect) ───────────────────────────────


class LinkedInOAuthStartRequest(BaseModel):
    redirect_uri: Optional[str] = Field(
        default=None,
        description="Must match an authorized redirect URL in the LinkedIn app",
    )


def _encode_linkedin_oauth_state(ctx: dict) -> str:
    payload = {
        "redirect_uri": (ctx.get("redirect_uri") or "").strip(),
        "tenant_id": ctx.get("tenant_id"),
        "user_id": ctx.get("user_id"),
        "exp": int(time.time()) + _OAUTH_STATE_TTL_SEC,
        "nonce": secrets.token_urlsafe(8),
        "provider": "linkedin",
    }
    raw = json.dumps(payload, separators=(",", ":"))
    token = encrypt_text(raw) or raw
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def _decode_linkedin_oauth_state(state: str | None) -> dict | None:
    if not state:
        return None
    try:
        token = base64.urlsafe_b64decode(state.encode("ascii")).decode("utf-8")
    except Exception:
        return None
    try:
        raw = decrypt_text(token)
    except Exception:
        raw = None
    try:
        data = json.loads(raw or token or "")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("provider") != "linkedin":
        return None
    if int(data.get("exp") or 0) < int(time.time()):
        return None
    return data


def _linkedin_app_path() -> str:
    return (os.getenv("AUTOREACH_APP_PATH", "/app") or "/app").rstrip("/") or "/app"


def _linkedin_oauth_error_redirect(error: str) -> RedirectResponse:
    q = urlencode({"linkedin_error": error})
    return RedirectResponse(url=f"{_linkedin_app_path()}/operations/linkedin?{q}", status_code=302)


def _linkedin_oauth_success_redirect() -> RedirectResponse:
    return RedirectResponse(
        url=f"{_linkedin_app_path()}/operations/linkedin?linkedin=connected",
        status_code=302,
    )


def _resolve_linkedin_redirect_uri(redirect_uri: str | None, request: Request) -> str:
    configured = (os.getenv("LINKEDIN_OAUTH_REDIRECT_URI") or "").strip()
    if redirect_uri and redirect_uri.strip():
        return redirect_uri.strip()
    if configured:
        return configured
    # Same-origin callback under the API, mirroring Gmail mailbox OAuth.
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/linkedin/oauth/callback"


def _validate_linkedin_redirect_uri(redirect_uri: str, *, request: Request) -> None:
    parsed = urlparse(redirect_uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(400, "Invalid LinkedIn redirect_uri")
    req_host = urlparse(str(request.base_url)).netloc.lower()
    if parsed.netloc.lower() != req_host:
        public = (os.getenv("AUTOREACH_PUBLIC_BASE_URL") or "").strip()
        allowed = {req_host}
        if public:
            allowed.add(urlparse(public).netloc.lower())
        if parsed.netloc.lower() not in allowed:
            raise HTTPException(400, "LinkedIn redirect_uri host is not allowed")


def _persist_linkedin_oauth_seat(
    *,
    store: Any,
    tenant_id: str,
    user_id: str,
    tokens: dict,
    profile: dict,
) -> Dict[str, Any]:
    _ensure_linkedin_seats_table(store)
    public_id = str(profile.get("public_identifier") or profile.get("sub") or "linkedin-user")
    seat_id = f"liseat_{hashlib.sha1(f'{tenant_id}:oauth:{public_id}'.encode('utf-8')).hexdigest()[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    access_enc = _encrypt_cookie(str(tokens.get("access_token") or ""))
    refresh_enc = _encrypt_cookie(str(tokens.get("refresh_token") or "")) if tokens.get("refresh_token") else ""
    expires_in = tokens.get("expires_in")
    token_expires_at = ""
    if expires_in is not None:
        try:
            token_expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            ).isoformat()
        except (TypeError, ValueError):
            token_expires_at = ""
    scopes = str(tokens.get("scope") or "openid profile email")
    account_name = str(profile.get("full_name") or "LinkedIn member")
    email = str(profile.get("email") or "")
    member_urn = str(profile.get("member_urn") or "")
    headline = str(profile.get("headline") or "")

    engine = store._holder.engine
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM linkedin_seats WHERE id = :id"),
            {"id": seat_id},
        ).first()
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE linkedin_seats
                    SET account_name = :account_name,
                        public_identifier = :public_id,
                        member_urn = :member_urn,
                        headline = :headline,
                        email = :email,
                        access_token_encrypted = :access_enc,
                        refresh_token_encrypted = :refresh_enc,
                        token_expires_at = :token_expires_at,
                        oauth_scopes = :scopes,
                        li_at_encrypted = COALESCE(NULLIF(li_at_encrypted, ''), ''),
                        jsession_id_encrypted = COALESCE(NULLIF(jsession_id_encrypted, ''), ''),
                        status = 'connected',
                        mode = 'openid',
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": seat_id,
                    "account_name": account_name,
                    "public_id": public_id,
                    "member_urn": member_urn,
                    "headline": headline,
                    "email": email,
                    "access_enc": access_enc,
                    "refresh_enc": refresh_enc,
                    "token_expires_at": token_expires_at,
                    "scopes": scopes,
                    "updated_at": now,
                },
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO linkedin_seats (
                        id, tenant_id, user_id, account_name, public_identifier, member_urn,
                        headline, li_at_encrypted, jsession_id_encrypted, proxy_url,
                        daily_connection_limit, daily_message_limit, daily_profile_views_limit,
                        connections_sent_today, messages_sent_today, status, mode,
                        created_at, updated_at, email, access_token_encrypted,
                        refresh_token_encrypted, token_expires_at, oauth_scopes
                    ) VALUES (
                        :id, :tenant_id, :user_id, :account_name, :public_id, :member_urn,
                        :headline, '', '', NULL,
                        25, 50, 80,
                        0, 0, 'connected', 'openid',
                        :created_at, :updated_at, :email, :access_enc,
                        :refresh_enc, :token_expires_at, :scopes
                    )
                    """
                ),
                {
                    "id": seat_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "account_name": account_name,
                    "public_id": public_id,
                    "member_urn": member_urn,
                    "headline": headline,
                    "created_at": now,
                    "updated_at": now,
                    "email": email,
                    "access_enc": access_enc,
                    "refresh_enc": refresh_enc,
                    "token_expires_at": token_expires_at,
                    "scopes": scopes,
                },
            )

    return {
        "ok": True,
        "seat_id": seat_id,
        "auth_method": "linkedin_oauth",
        "seat": {
            "id": seat_id,
            "tenant_id": tenant_id,
            "account_name": account_name,
            "public_identifier": public_id,
            "member_urn": member_urn,
            "email": email,
            "headline": headline,
            "status": "connected",
            "mode": "openid",
            "auth_method": "linkedin_oauth",
            "can_auto_message": False,
            "oauth_scopes": scopes,
            "updated_at": now,
        },
    }


@router.get("/oauth/config")
def linkedin_oauth_config() -> Dict[str, Any]:
    """Public-ish (auth still required via SPA) config for the LinkedIn page."""
    return {
        "configured": linkedin_oauth_configured(),
        "client_id_present": bool(linkedin_client_id()),
        "scopes": ["openid", "profile", "email"],
        "docs": "https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2",
        "capability_note": (
            "Official Sign In with LinkedIn verifies the member. "
            "It does not authorize automated connection requests or DMs."
        ),
    }


@router.post("/oauth/start")
def linkedin_oauth_start(
    body: LinkedInOAuthStartRequest,
    request: Request,
    user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    if not linkedin_oauth_configured():
        raise HTTPException(
            503,
            "LinkedIn OAuth is not configured. Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET "
            "(create an app at https://www.linkedin.com/developers/apps).",
        )
    redirect_uri = _resolve_linkedin_redirect_uri(body.redirect_uri, request)
    _validate_linkedin_redirect_uri(redirect_uri, request=request)
    state = _encode_linkedin_oauth_state(
        {
            "redirect_uri": redirect_uri,
            "tenant_id": _get_tenant_id(user),
            "user_id": _get_user_id(user),
        }
    )
    auth_url = build_authorization_url(redirect_uri=redirect_uri, state=state)
    return {"authorization_url": auth_url, "state": state, "redirect_uri": redirect_uri}


@router.get("/oauth/callback")
def linkedin_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    store: Any = Depends(get_store),
):
    if error:
        return _linkedin_oauth_error_redirect(error_description or error)
    ctx = _decode_linkedin_oauth_state(state)
    if not ctx or not code:
        return _linkedin_oauth_error_redirect("invalid_or_expired_state")
    redirect_uri = (ctx.get("redirect_uri") or "").strip()
    tenant_id = ctx.get("tenant_id")
    user_id = ctx.get("user_id")
    if not redirect_uri or not tenant_id:
        return _linkedin_oauth_error_redirect("invalid_or_expired_state")
    try:
        tokens = exchange_code_for_tokens(code=code, redirect_uri=redirect_uri)
        userinfo = fetch_userinfo(str(tokens["access_token"]))
        profile = normalize_profile(userinfo)
        _persist_linkedin_oauth_seat(
            store=store,
            tenant_id=str(tenant_id),
            user_id=str(user_id or "user"),
            tokens=tokens,
            profile=profile,
        )
    except Exception as exc:
        return _linkedin_oauth_error_redirect(str(exc)[:120] or "token_exchange_failed")
    return _linkedin_oauth_success_redirect()

