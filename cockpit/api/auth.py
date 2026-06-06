"""
POST /api/auth/signup   — create tenant + owner user → JWT
POST /api/auth/login    — verify credentials → JWT
GET  /api/auth/me       — current user info
POST /api/auth/refresh  — exchange refresh token → new access token
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

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


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


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
    tenant = Tenant(
        id=_new_id("tnt"),
        name=body.company_name.strip() or email.split("@")[0],
        plan="free",
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
    plan = tenant.plan if tenant else "free"
    return _make_tokens(user, plan)


@router.get("/me", response_model=MeResponse)
def me(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    user = store.get_user(current_user.user_id)
    tenant = store.get_tenant(current_user.tenant_id)
    return MeResponse(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        email=current_user.email,
        full_name=user.full_name if user else "",
        role=current_user.role,
        plan=current_user.plan,
        tenant_name=tenant.name if tenant else "",
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
    plan = tenant.plan if tenant else "free"
    return _make_tokens(user, plan)
