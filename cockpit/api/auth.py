"""
POST /api/auth/signup        — create tenant + owner user → JWT
POST /api/auth/login         — verify credentials → JWT
POST /api/auth/google        — exchange a Google ID token → JWT (social login)
GET  /api/auth/me            — current user info
GET  /api/auth/social-config — which social providers are enabled (public)
POST /api/auth/refresh       — exchange refresh token → new access token
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from cockpit.api.deps import get_current_user, get_store
from engine.auth import (
    CurrentUser,
    Tenant,
    User,
    decode_jwt,
    hash_password,
    sign_jwt,
    verify_password,
    InvalidTokenError,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# New accounts get a 7-day Pro trial (full features, no card required).
TRIAL_DAYS = 7


class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""
    company_name: str = ""

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email address")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str


class GoogleLoginRequest(BaseModel):
    credential: str  # the Google ID token (JWT) from Google Identity Services


class SocialConfigResponse(BaseModel):
    google_enabled: bool
    google_client_id: str = ""


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    tenant_id: str
    email: str
    role: str
    plan: str


class MeResponse(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    full_name: str
    role: str
    plan: str
    tenant_name: str
    trial_active: bool = False
    trial_days_left: int = 0


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _effective_plan(tenant) -> str:
    """
    The plan a tenant is actually entitled to right now.

    During an active trial, `trial_ends_at` is in the future and tenant.plan is
    the trial tier (pro). Once the trial lapses without a paid upgrade (paid
    upgrades clear trial_ends_at), the effective plan falls back to 'free'.
    """
    if tenant is None:
        return "free"
    trial_ends = getattr(tenant, "trial_ends_at", None)
    if trial_ends is not None:
        if trial_ends.tzinfo is None:
            trial_ends = trial_ends.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= trial_ends:
            return "free"
    return tenant.plan


def _make_tokens(user: User, plan: str) -> TokenResponse:
    access = sign_jwt(
        user_id=user.id, tenant_id=user.tenant_id,
        email=user.email, role=user.role, plan=plan,
        token_type="access",
    )
    refresh = sign_jwt(
        user_id=user.id, tenant_id=user.tenant_id,
        email=user.email, role=user.role, plan=plan,
        token_type="refresh",
    )
    return TokenResponse(
        access_token=access, refresh_token=refresh,
        user_id=user.id, tenant_id=user.tenant_id,
        email=user.email, role=user.role, plan=plan,
    )


# ─── Routes ───────────────────────────────────────────────────────────────────


@router.post("/signup", response_model=TokenResponse)
def signup(body: SignupRequest, store=Depends(get_store)):
    email = body.email.lower().strip()

    if store.get_user_by_email(email):
        raise HTTPException(409, "An account with this email already exists")

    now = datetime.now(timezone.utc)
    # Every new account starts on a 7-day Pro trial — full features, no card.
    tenant = Tenant(
        id=_new_id("tnt"),
        name=body.company_name.strip() or email.split("@")[0],
        plan="pro",
        trial_ends_at=now + timedelta(days=TRIAL_DAYS),
        created_at=now, updated_at=now,
    )
    store.save_tenant(tenant)

    user = User(
        id=_new_id("usr"),
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name.strip(),
        role="owner",
        is_active=True,
        created_at=now, updated_at=now,
    )
    store.save_user(user)

    return _make_tokens(user, tenant.plan)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, store=Depends(get_store)):
    email = body.email.lower().strip()
    user = store.get_user_by_email(email)
    if user is None or not user.is_active:
        raise HTTPException(401, "Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

    tenant = store.get_tenant(user.tenant_id)
    plan = _effective_plan(tenant)
    return _make_tokens(user, plan)


# ─── Social login (Google Identity Services) ───────────────────────────────────


def _google_client_id() -> str:
    """Client ID used to sign in users. Falls back to the Gmail OAuth client."""
    return (
        os.getenv("GOOGLE_SIGNIN_CLIENT_ID")
        or os.getenv("GOOGLE_CLIENT_ID")
        or ""
    )


@router.get("/social-config", response_model=SocialConfigResponse)
def social_config():
    """Public: lets the SPA decide whether to render social-login buttons."""
    client_id = _google_client_id()
    return SocialConfigResponse(
        google_enabled=bool(client_id),
        google_client_id=client_id,
    )


@router.post("/google", response_model=TokenResponse)
def google_login(body: GoogleLoginRequest, store=Depends(get_store)):
    client_id = _google_client_id()
    if not client_id:
        raise HTTPException(503, "Google sign-in is not configured on this server")

    # Verify the ID token signature + audience against Google's public keys.
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
    except ImportError as exc:  # pragma: no cover - dependency always present in prod
        raise HTTPException(503, "Google auth libraries unavailable") from exc

    try:
        claims = google_id_token.verify_oauth2_token(
            body.credential,
            google_requests.Request(),
            client_id,
            clock_skew_in_seconds=10,
        )
    except ValueError as exc:
        raise HTTPException(401, "Invalid Google credential") from exc

    if not claims.get("email_verified"):
        raise HTTPException(401, "Google account email is not verified")

    email = (claims.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(401, "Google credential did not include an email")

    user = store.get_user_by_email(email)
    now = datetime.now(timezone.utc)

    if user is None:
        # First-time social sign-in → provision tenant + owner user.
        full_name = claims.get("name", "")
        tenant = Tenant(
            id=_new_id("tnt"),
            name=email.split("@")[0],
            plan="pro",
            trial_ends_at=now + timedelta(days=TRIAL_DAYS),
            created_at=now, updated_at=now,
        )
        store.save_tenant(tenant)
        # No usable password — store an unguessable random hash. Social users
        # authenticate via Google, never via the password login path.
        user = User(
            id=_new_id("usr"),
            tenant_id=tenant.id,
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            full_name=full_name,
            role="owner",
            is_active=True,
            created_at=now, updated_at=now,
        )
        store.save_user(user)
        plan = tenant.plan
    else:
        if not user.is_active:
            raise HTTPException(403, "This account is disabled")
        tenant = store.get_tenant(user.tenant_id)
        plan = _effective_plan(tenant)

    return _make_tokens(user, plan)


@router.get("/me", response_model=MeResponse)
def me(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    user = store.get_user(current_user.user_id)
    tenant = store.get_tenant(current_user.tenant_id)

    trial_active = False
    trial_days_left = 0
    trial_ends = getattr(tenant, "trial_ends_at", None) if tenant else None
    if trial_ends is not None:
        if trial_ends.tzinfo is None:
            trial_ends = trial_ends.replace(tzinfo=timezone.utc)
        remaining = trial_ends - datetime.now(timezone.utc)
        if remaining.total_seconds() > 0:
            trial_active = True
            # Round up so the last partial day still reads as "1 day left".
            trial_days_left = max(1, -(-int(remaining.total_seconds()) // 86400))

    return MeResponse(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        email=current_user.email,
        full_name=user.full_name if user else "",
        role=current_user.role,
        plan=_effective_plan(tenant),
        tenant_name=tenant.name if tenant else "",
        trial_active=trial_active,
        trial_days_left=trial_days_left,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, store=Depends(get_store)):
    try:
        payload = decode_jwt(body.refresh_token, expected_type="refresh")
    except InvalidTokenError as exc:
        raise HTTPException(401, str(exc)) from exc

    user = store.get_user(payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(401, "User not found or inactive")

    tenant = store.get_tenant(user.tenant_id)
    plan = _effective_plan(tenant)
    return _make_tokens(user, plan)
