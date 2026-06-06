"""HS256 JWT sign + decode.

Tokens carry: sub (user_id), tenant_id, email, role, plan, type, exp.
Access tokens expire in 24 h; refresh tokens in 30 days.

Secret: AUTOREACH_JWT_SECRET env var. Falls back to a dev default that
ALWAYS logs a loud warning — never silently pass weak secrets to prod.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt  # PyJWT

logger = logging.getLogger(__name__)

_DEV_SECRET = "CHANGE_ME_SET_AUTOREACH_JWT_SECRET_IN_ENV"
_ALGORITHM = "HS256"
_ACCESS_EXPIRE_HOURS = 24
_REFRESH_EXPIRE_DAYS = 30


class AuthError(Exception):
    """Base auth error."""


class InvalidTokenError(AuthError):
    """JWT is missing, malformed, expired, or has wrong type."""


class UnauthorizedError(AuthError):
    """No Authorization header provided."""


def _secret() -> str:
    s = os.getenv("AUTOREACH_JWT_SECRET", "").strip()
    if not s:
        logger.warning(
            "AUTOREACH_JWT_SECRET not set — using insecure default. "
            "Set this env var before any production deployment."
        )
        return _DEV_SECRET
    return s


def sign_jwt(
    *,
    user_id: str,
    tenant_id: str,
    email: str,
    role: str,
    plan: str,
    token_type: str = "access",  # "access" | "refresh"
) -> str:
    """Create and sign a JWT. Returns the encoded token string."""
    now = datetime.now(timezone.utc)
    if token_type == "refresh":
        expire = now + timedelta(days=_REFRESH_EXPIRE_DAYS)
    else:
        expire = now + timedelta(hours=_ACCESS_EXPIRE_HOURS)

    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "role": role,
        "plan": plan,
        "type": token_type,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def decode_jwt(token: str, *, expected_type: str = "access") -> dict:
    """
    Decode and validate a JWT. Returns the payload dict.

    Raises:
        InvalidTokenError — on any decode or validation failure.
    """
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[_ALGORITHM],
            options={"require": ["exp", "sub", "tenant_id"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"invalid token: {exc}") from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenError(
            f"expected token type '{expected_type}', got '{payload.get('type')}'"
        )
    return payload
