"""Shared Google OAuth scopes for Gmail + Calendar (Attainly / AutoReach).

Mailbox connect and Calendar connect both request these scopes so a single
Google account refresh token can send mail and create Calendar events.
Existing mailboxes that connected before Calendar scopes were added need a
re-consent via POST /api/calendar/connect/start.
"""

from __future__ import annotations

import os

GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_EVENTS = "https://www.googleapis.com/auth/calendar.events"
CALENDAR_FREEBUSY = "https://www.googleapis.com/auth/calendar.freebusy"
OPENID = "openid"
USERINFO_EMAIL = "https://www.googleapis.com/auth/userinfo.email"
USERINFO_PROFILE = "https://www.googleapis.com/auth/userinfo.profile"

# Full consent set for mailbox + native Calendar booking.
# Include userinfo.profile: Google OIDC adds it whenever openid/email is
# requested, and oauthlib otherwise treats that as a fatal scope change.
GOOGLE_MAILBOX_SCOPES: list[str] = [
    GMAIL_SEND,
    GMAIL_READONLY,
    CALENDAR_EVENTS,
    CALENDAR_FREEBUSY,
    OPENID,
    USERINFO_EMAIL,
    USERINFO_PROFILE,
]


def relax_oauthlib_token_scope() -> None:
    """Allow Google to return a superset of requested scopes on token exchange.

    google-auth-oauthlib/oauthlib raises ``Warning: Scope has changed`` (an
    unhandled 500) when Google adds OIDC profile or previously granted scopes
    via ``include_granted_scopes``. Calendar connect already needed this;
    mailbox connect must match.
    """
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

# Minimum scopes required to query free/busy and create invite events.
CALENDAR_REQUIRED_SCOPES: frozenset[str] = frozenset({CALENDAR_EVENTS})


def normalize_scopes(scopes: list[str] | tuple[str, ...] | None) -> list[str]:
    if not scopes:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for s in scopes:
        s = (s or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def has_calendar_scopes(scopes: list[str] | tuple[str, ...] | None) -> bool:
    granted = set(normalize_scopes(scopes))
    return CALENDAR_EVENTS in granted


def missing_calendar_scopes(scopes: list[str] | tuple[str, ...] | None) -> list[str]:
    granted = set(normalize_scopes(scopes))
    return sorted(s for s in (CALENDAR_EVENTS, CALENDAR_FREEBUSY) if s not in granted)
