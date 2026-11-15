"""
M4 — DbTokenStore: database-backed Gmail credentials.

Implements the same `GmailTokenStore` protocol as JsonFileTokenStore, but
reads/writes credentials from the `mailboxes` table instead of disk. This is
the multi-tenant unlock: each customer's mailbox row carries its own OAuth
credentials, refreshed independently.

Because RealGmailSendAdapter already accepts any `GmailTokenStore`, this drops
in with zero adapter changes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from engine.adapters.gmail_token_store import (
    MISSING_REFRESH_TOKEN_ERROR,
    TokenInvalid,
    TokenUnavailable,
    authorized_user_info_from_credentials,
    build_google_credentials,
    gmail_credentials_are_sendable,
)
from engine.debug_agent import agent_debug
from engine.adapters.google_scopes import GOOGLE_MAILBOX_SCOPES

logger = logging.getLogger(__name__)


class DbTokenStore:
    """Per-mailbox token store backed by the engine's Store."""

    def __init__(self, *, store, mailbox_id: str) -> None:
        self._store = store
        self._mailbox_id = mailbox_id

    @property
    def mailbox_id(self) -> str:
        return self._mailbox_id

    def load(self) -> "object":
        mailbox = self._store.get_mailbox(self._mailbox_id)
        if mailbox is None:
            raise TokenUnavailable(f"mailbox not found: {self._mailbox_id}")
        if mailbox.status == "revoked":
            raise TokenInvalid(mailbox.last_error or "mailbox marked revoked")
        if not mailbox.credentials_json:
            raise TokenUnavailable(f"mailbox {self._mailbox_id} has no credentials")

        info = dict(mailbox.credentials_json)
        info.setdefault("token_uri", "https://oauth2.googleapis.com/token")
        info.setdefault("client_id", mailbox.oauth_client_id or "")
        info.setdefault("client_secret", mailbox.oauth_client_secret or "")
        ok, reason = gmail_credentials_are_sendable(info)
        agent_debug(
            "A",
            "db_token_store.py:load",
            "mailbox load flags",
            {
                "mailbox_id": self._mailbox_id,
                "has_refresh_token": bool(str(info.get("refresh_token") or "").strip()),
                "has_access_token": bool(str(info.get("token") or info.get("access_token") or "").strip()),
                "sendable": ok,
                "reason": (reason or "")[:160],
                "cred_keys": sorted(list(info.keys())),
            },
        )
        if not ok:
            self._record_send_error(reason)
            raise TokenInvalid(reason)

        try:
            from google.auth.exceptions import RefreshError  # type: ignore
            from google.auth.transport.requests import Request  # type: ignore
            creds = build_google_credentials(
                info, scopes=info.get("scopes") or list(GOOGLE_MAILBOX_SCOPES)
            )
        except Exception as exc:  # pragma: no cover
            detail = str(exc or "")
            if "refresh_token" in detail.lower():
                reason = MISSING_REFRESH_TOKEN_ERROR
            else:
                reason = f"gmail credentials unusable: {type(exc).__name__}"
            self._record_send_error(reason)
            raise TokenInvalid(reason) from exc

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                self.mark_invalid(f"refresh failed: {exc}")
                raise TokenInvalid(str(exc)) from exc
            self.save(creds)
        elif creds.expired:
            self._record_send_error(MISSING_REFRESH_TOKEN_ERROR)
            raise TokenInvalid(MISSING_REFRESH_TOKEN_ERROR)

        return creds

    def save(self, credentials: "object") -> None:
        mailbox = self._store.get_mailbox(self._mailbox_id)
        if mailbox is None:
            return
        info = authorized_user_info_from_credentials(
            credentials,
            fallback_client_id=mailbox.oauth_client_id or "",
            fallback_client_secret=mailbox.oauth_client_secret or "",
            existing=dict(mailbox.credentials_json or {}),
        )
        self._store.update_mailbox_credentials(self._mailbox_id, credentials_json=dict(info))

    def _record_send_error(self, reason: str) -> None:
        mailbox = self._store.get_mailbox(self._mailbox_id)
        if mailbox is None:
            return
        status = getattr(mailbox, "status", None) or "active"
        self._store.update_mailbox_status(
            self._mailbox_id, status=status, last_error=(reason or "")[:500]
        )

    def mark_invalid(self, reason: str) -> None:
        self._store.update_mailbox_status(self._mailbox_id, status="revoked", last_error=reason[:500])

    def is_invalid(self) -> bool:
        mailbox = self._store.get_mailbox(self._mailbox_id)
        return mailbox is not None and mailbox.status == "revoked"
