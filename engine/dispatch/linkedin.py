from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

from .linkedin_provider import (
    LinkedInMessage,
    LinkedInMultiChannelStrategy,
    LinkedInPostEngager,
    LinkedInProfile,
    LinkedInProvider,
    build_voyager_headers,
    extract_activity_urn,
    extract_public_id,
    split_linkedin_messages_into_conversation,
    strip_jsessionid_quotes,
)

logger = logging.getLogger(__name__)

_LINKEDIN_SEAT_STATUSES = frozenset({"connected", "active", "healthy", "ready"})


def tenant_has_linkedin_seat(store: Any, tenant_id: Optional[str]) -> bool:
    """True when LinkedIn *automation* can run (legacy Voyager cookie seat).

    Official Sign In with LinkedIn (OIDC) verifies identity but does **not**
    authorize cold DMs / connection requests. Those OAuth seats must not keep
    LinkedIn-first sequence steps — they fall back to email.
    """
    if not tenant_id:
        return False
    holder = getattr(store, "_holder", None)
    engine = getattr(holder, "engine", None)
    if engine is None:
        return False
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, status, li_at_encrypted, mode,
                           access_token_encrypted
                    FROM linkedin_seats
                    WHERE tenant_id = :tid
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ),
                {"tid": tenant_id},
            ).mappings().first()
    except Exception:
        # Older DBs without oauth columns — retry cookie-only.
        try:
            from sqlalchemy import text

            with engine.begin() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT id, status, li_at_encrypted
                        FROM linkedin_seats
                        WHERE tenant_id = :tid
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """
                    ),
                    {"tid": tenant_id},
                ).mappings().first()
        except Exception:
            logger.debug("linkedin seat lookup failed tenant=%s", tenant_id, exc_info=True)
            return False
    if not row:
        return False
    status = str(row.get("status") or "").strip().lower()
    if status in {"revoked", "disconnected", "error", "expired"}:
        return False
    mode = str(row.get("mode") or "").strip().lower()
    if mode in {"openid", "oauth", "oauth_openid"}:
        return False  # identity-only; no Voyager automation
    return bool(row.get("li_at_encrypted"))


class LinkedInDispatchProvider:
    """LinkedIn Voyager dispatch provider for connection requests, DMs, profile views, and post likes."""

    def __init__(
        self,
        session_cookie: Optional[str] = None,
        jsession_id: Optional[str] = None,
        proxy_url: Optional[str] = None,
    ) -> None:
        self._cookie = session_cookie or os.getenv("AUTOREACH_LINKEDIN_LI_AT")
        self._jsession_id = jsession_id or os.getenv("AUTOREACH_LINKEDIN_JSESSIONID")
        self._proxy_url = proxy_url or os.getenv("AUTOREACH_LINKEDIN_PROXY_URL")

    @property
    def name(self) -> str:
        return "linkedin_voyager"

    def dispatch(self, job: Any) -> str:
        payload = getattr(job, "payload", {}) or {}
        profile_url = (
            payload.get("linkedin_url")
            or payload.get("profile_url")
            or getattr(job, "to_email", "")
        )
        body = payload.get("body", "")
        step_type = payload.get("step_type", "linkedin_dm")
        split_bubbles = bool(payload.get("splitLinkedinMessagesIntoConversation", False))

        if not profile_url:
            raise ValueError("Cannot dispatch LinkedIn job: missing target LinkedIn URL or handle.")

        provider = LinkedInProvider(
            li_at=self._cookie,
            jsession_id=self._jsession_id,
            proxy_url=self._proxy_url,
        )

        if step_type in ("visitProfile", "linkedin_visit"):
            res = provider.visit_profile_sync(profile_url)
            return f"li_visit_{res.get('entity_urn', uuid.uuid4().hex[:12])}"
        if step_type in ("likePosts", "linkedin_like"):
            provider.like_posts_sync(profile_url, count=int(payload.get("count", 2)))
            return f"li_like_{uuid.uuid4().hex[:12]}"
        if step_type in ("invitation", "invitationNote", "linkedin_connect", "connection_request"):
            res = provider.send_invitation_sync(
                profile_url,
                custom_message=body if step_type != "invitation" else None,
            )
            return f"li_inv_{res.get('inviteeProfileUrn', uuid.uuid4().hex[:12])}"

        res = provider.send_message_sync(
            profile_url,
            body or "Hi! Wanted to connect.",
            split_into_conversation=split_bubbles,
        )
        return str(res.get("linkedinMessageBackendUrn") or f"li_msg_{uuid.uuid4().hex[:12]}")


def get_active_linkedin_provider(
    store: Any,
    tenant_id: str,
    seat_id: Optional[str] = None,
) -> LinkedInProvider:
    """Load the tenant's Voyager seat cookies and return a LinkedInProvider."""
    from engine.security.secrets import decrypt_text
    from sqlalchemy import text

    holder = getattr(store, "_holder", None)
    engine = getattr(holder, "engine", None)
    if engine is None:
        return LinkedInProvider()

    def _decrypt(value: str) -> str:
        if not value:
            return ""
        try:
            out = decrypt_text(value)
            if out and not str(out).startswith("enc:v1:"):
                return out
        except Exception:
            pass
        return value

    try:
        with engine.begin() as conn:
            if seat_id:
                row = conn.execute(
                    text(
                        "SELECT * FROM linkedin_seats WHERE id = :id AND tenant_id = :tid"
                    ),
                    {"id": seat_id, "tid": tenant_id},
                ).mappings().first()
            else:
                row = conn.execute(
                    text(
                        """
                        SELECT * FROM linkedin_seats
                        WHERE tenant_id = :tid
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """
                    ),
                    {"tid": tenant_id},
                ).mappings().first()
    except Exception:
        logger.debug("get_active_linkedin_provider failed tenant=%s", tenant_id, exc_info=True)
        return LinkedInProvider()

    if not row:
        return LinkedInProvider()

    return LinkedInProvider(
        li_at=_decrypt(str(row.get("li_at_encrypted") or "")),
        jsession_id=_decrypt(str(row.get("jsession_id_encrypted") or "")),
        proxy_url=row.get("proxy_url"),
    )


__all__ = [
    "LinkedInProvider",
    "LinkedInDispatchProvider",
    "tenant_has_linkedin_seat",
    "get_active_linkedin_provider",
    "LinkedInProfile",
    "LinkedInMessage",
    "LinkedInPostEngager",
    "LinkedInMultiChannelStrategy",
    "build_voyager_headers",
    "extract_activity_urn",
    "extract_public_id",
    "split_linkedin_messages_into_conversation",
    "strip_jsessionid_quotes",
]
