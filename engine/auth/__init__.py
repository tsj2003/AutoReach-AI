"""
engine.auth — JWT authentication + multi-tenant primitives.

Public surface:
    Tenant              frozen dataclass
    User                frozen dataclass
    hash_password       bcrypt hash
    verify_password     bcrypt verify
    sign_jwt            HS256 JWT creation
    decode_jwt          HS256 JWT decode + validation
    JWTBearer           FastAPI dependency class
    CurrentUser         context object returned by JWTBearer
    AuthError           base exception
    InvalidTokenError   raised on bad/expired JWT
    UnauthorizedError   raised on missing auth header
"""

from engine.auth.models import CurrentUser, Tenant, User  # noqa: F401
from engine.auth.password import hash_password, verify_password  # noqa: F401
from engine.auth.jwt_handler import (  # noqa: F401
    AuthError,
    InvalidTokenError,
    UnauthorizedError,
    decode_jwt,
    sign_jwt,
)
from engine.auth.jwt_bearer import get_current_user_dep as JWTBearer  # noqa: F401

__all__ = [
    "Tenant",
    "User",
    "CurrentUser",
    "hash_password",
    "verify_password",
    "sign_jwt",
    "decode_jwt",
    "JWTBearer",
    "AuthError",
    "InvalidTokenError",
    "UnauthorizedError",
]
