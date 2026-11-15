"""FastAPI dependency that validates JWT and injects CurrentUser."""

from __future__ import annotations

from fastapi import HTTPException, Request

from engine.auth.jwt_handler import AuthError, InvalidTokenError, decode_jwt
from engine.auth.models import CurrentUser


async def get_current_user_dep(request: Request) -> CurrentUser:
    """
    FastAPI dependency. Reads the Bearer token from the Authorization header,
    decodes + validates it, and returns a CurrentUser context object.

    Usage:
        from fastapi import Depends
        from engine.auth.jwt_bearer import get_current_user_dep

        @router.get("/protected")
        def handler(user: CurrentUser = Depends(get_current_user_dep)):
            ...

    Raises HTTP 401 on any auth failure.
    """
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(401, "Authorization header missing or malformed")

    try:
        payload = decode_jwt(token)
    except InvalidTokenError as exc:
        raise HTTPException(401, str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(503, "JWT signing secret is not configured") from exc

    return CurrentUser(
        user_id=payload["sub"],
        tenant_id=payload["tenant_id"],
        email=payload.get("email", ""),
        role=payload.get("role", "member"),
        plan=payload.get("plan", "free"),
    )


class JWTBearer:
    """Class-based wrapper kept for backward compat. Prefer get_current_user_dep."""

    def __call__(self) -> "type[get_current_user_dep]":
        return get_current_user_dep
