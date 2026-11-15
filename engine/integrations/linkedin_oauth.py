"""Official LinkedIn Sign-In (OpenID Connect) — no cookie scraping.

Docs: https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2

Env:
  LINKEDIN_CLIENT_ID
  LINKEDIN_CLIENT_SECRET
  LINKEDIN_OAUTH_REDIRECT_URI  (optional; otherwise request-built callback)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
# Sign In with LinkedIn using OpenID Connect — official self-serve scopes.
DEFAULT_SCOPES = ("openid", "profile", "email")


def linkedin_client_id() -> str:
    return (
        os.getenv("LINKEDIN_CLIENT_ID", "").strip()
        or os.getenv("AUTOREACH_LINKEDIN_CLIENT_ID", "").strip()
    )


def linkedin_client_secret() -> str:
    return (
        os.getenv("LINKEDIN_CLIENT_SECRET", "").strip()
        or os.getenv("AUTOREACH_LINKEDIN_CLIENT_SECRET", "").strip()
    )


def linkedin_oauth_configured() -> bool:
    return bool(linkedin_client_id() and linkedin_client_secret())


def build_authorization_url(*, redirect_uri: str, state: str, scopes: tuple[str, ...] = DEFAULT_SCOPES) -> str:
    params = {
        "response_type": "code",
        "client_id": linkedin_client_id(),
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": " ".join(scopes),
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(*, code: str, redirect_uri: str) -> dict[str, Any]:
    """Exchange auth code for access (+ refresh when LinkedIn issues one)."""
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": linkedin_client_id(),
            "client_secret": linkedin_client_secret(),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"linkedin_token_exchange_failed:{exc.code}:{detail}") from exc
    data = json.loads(raw)
    if not data.get("access_token"):
        raise RuntimeError("linkedin_token_exchange_missing_access_token")
    return data


def fetch_userinfo(access_token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"linkedin_userinfo_failed:{exc.code}:{detail}") from exc
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("linkedin_userinfo_invalid")
    return data


def normalize_profile(userinfo: dict[str, Any]) -> dict[str, Optional[str]]:
    """Map OIDC userinfo into seat display fields."""
    sub = str(userinfo.get("sub") or "").strip()
    name = str(userinfo.get("name") or "").strip()
    given = str(userinfo.get("given_name") or "").strip()
    family = str(userinfo.get("family_name") or "").strip()
    if not name:
        name = " ".join(p for p in (given, family) if p).strip()
    email = str(userinfo.get("email") or "").strip() or None
    picture = str(userinfo.get("picture") or "").strip() or None
    # Locale / vanity are not always present on userinfo.
    return {
        "sub": sub or None,
        "full_name": name or "LinkedIn member",
        "email": email,
        "picture": picture,
        "public_identifier": sub or email or "linkedin-user",
        "member_urn": f"urn:li:person:{sub}" if sub else "",
        "headline": "",
    }
