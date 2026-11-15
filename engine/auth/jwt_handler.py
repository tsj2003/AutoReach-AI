"""HS256 JWT sign + decode.

Tokens carry: sub (user_id), tenant_id, email, role, plan, type, exp.
Access tokens expire in 24 h; refresh tokens in 30 days.

Secret: AUTOREACH_JWT_SECRET env var. Local/dev falls back to a dev default
with a loud warning; production-like deployments fail closed.
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

# Repo-public sentinels that must never be accepted as a real signing secret.
# The deploy templates ship "REPLACE_WITH_GENERATED_SECRET"; if an operator
# forgets to override it, the signing key is public in git and any tenant's
# token could be forged. Treat these as "unset" so production fails closed.
_PLACEHOLDER_MARKERS = ("REPLACE_WITH", "CHANGE_ME", "YOUR_SECRET", "EXAMPLE")


def _is_placeholder_secret(value: str) -> bool:
    if not value:
        return True
    upper = value.upper()
    return any(marker in upper for marker in _PLACEHOLDER_MARKERS)


class AuthError(Exception):
    """Base auth error."""


class InvalidTokenError(AuthError):
    """JWT is missing, malformed, expired, or has wrong type."""


class UnauthorizedError(AuthError):
    """No Authorization header provided."""


def _secret() -> str:
    s = os.getenv("AUTOREACH_JWT_SECRET", "").strip()
    production_like = _production_like()
    if production_like and _is_placeholder_secret(s):
        raise AuthError(
            "AUTOREACH_JWT_SECRET is missing or still set to a placeholder. "
            "Set a strong, unique secret before any production deployment."
        )
    if _is_placeholder_secret(s):
        logger.warning(
            "AUTOREACH_JWT_SECRET is unset or a placeholder — using insecure dev "
            "default. Set this env var before any production deployment."
        )
        return _DEV_SECRET
    return s


def is_production_like() -> bool:
    """Heuristic: console disabled + a non-sqlite DATABASE_URL looks like prod."""
    console_disabled = os.getenv("AUTOREACH_ENABLE_CONSOLE", "").strip().lower() in {
        "0", "false", "no", "off",
    }
    database_url = os.getenv("DATABASE_URL", "").strip().lower()
    return console_disabled and bool(database_url) and not database_url.startswith("sqlite:")


# Back-compat alias.
_production_like = is_production_like


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
