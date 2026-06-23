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

from engine.adapters.gmail_token_store import TokenInvalid, TokenUnavailable

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

        try:
            from google.oauth2.credentials import Credentials  # type: ignore
            from google.auth.exceptions import RefreshError  # type: ignore
            from google.auth.transport.requests import Request  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise TokenUnavailable(f"google-auth not installed: {exc}") from exc

        info = dict(mailbox.credentials_json)
        info.setdefault("token_uri", "https://oauth2.googleapis.com/token")
        info.setdefault("client_id", mailbox.oauth_client_id or "")
        info.setdefault("client_secret", mailbox.oauth_client_secret or "")
        creds = Credentials.from_authorized_user_info(
            info,
            scopes=info.get("scopes") or [
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.readonly",
            ],
        )

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                self.mark_invalid(f"refresh failed: {exc}")
                raise TokenInvalid(str(exc)) from exc
            self.save(creds)
        elif creds.expired:
            self.mark_invalid("token expired and no refresh_token present")
            raise TokenInvalid("token expired and no refresh_token present")

        return creds

    def save(self, credentials: "object") -> None:
        mailbox = self._store.get_mailbox(self._mailbox_id)
        if mailbox is None:
            return
        if hasattr(credentials, "to_authorized_user_info"):
            info = credentials.to_authorized_user_info()
        else:
            info = {
                "token": getattr(credentials, "token", None),
                "refresh_token": getattr(credentials, "refresh_token", None),
                "token_uri": getattr(credentials, "token_uri", None),
                "client_id": getattr(credentials, "client_id", None),
                "client_secret": getattr(credentials, "client_secret", None),
                "scopes": list(getattr(credentials, "scopes", []) or []),
            }
        self._store.update_mailbox_credentials(self._mailbox_id, credentials_json=dict(info))

    def mark_invalid(self, reason: str) -> None:
        self._store.update_mailbox_status(self._mailbox_id, status="revoked", last_error=reason[:500])

    def is_invalid(self) -> bool:
        mailbox = self._store.get_mailbox(self._mailbox_id)
        return mailbox is not None and mailbox.status == "revoked"
