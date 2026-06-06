"""
GmailTokenStore — pluggable storage for Google OAuth credentials.

Why a protocol
--------------
Phase 3 reads the operator's `token.json` off disk. Phase 5 will store
per-customer tokens in the database (one engagement = one mailbox or rotation
pool). By keeping the read/write behind a protocol now, we avoid having to
touch the adapter when we make that switch.

Protocol contract
-----------------
* `load()` returns a fresh, refreshed `google.oauth2.credentials.Credentials`,
  or raises `TokenUnavailable` if no valid token exists.
* `save(creds)` persists a refreshed credential. The adapter calls this after
  google-auth refreshes a token in-memory so the next process can reuse it.
* `mark_invalid(reason)` flags a token as needing re-auth. Used after the
  adapter sees an invalid_grant / 401 / 403. The cockpit polls this to show
  a "reconnect mailbox" banner.

Errors
------
* `TokenUnavailable`     — no token configured (treat as non-retryable)
* `TokenInvalid`         — token exists but Gmail rejected it (non-retryable;
                            operator must reconnect)
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class TokenUnavailable(RuntimeError):
    """Raised when no token is configured for the requested mailbox."""


class TokenInvalid(RuntimeError):
    """Raised when a token exists but Google rejected it. Operator must reconnect."""


@runtime_checkable
class GmailTokenStore(Protocol):
    """Pluggable credential storage for the Gmail adapter."""

    def load(self) -> "object":
        """Return a fresh `google.oauth2.credentials.Credentials`, or raise."""

    def save(self, credentials: "object") -> None:
        """Persist a (possibly refreshed) credential."""

    def mark_invalid(self, reason: str) -> None:
        """Record that the token needs re-auth. Used by the cockpit."""

    def is_invalid(self) -> bool:
        """Quick check for cockpit/UI: 'show reconnect banner?'"""


# ─────────────────────────────────────────────────────────────────────────────
# JsonFileTokenStore — reads/writes `token.json` (the format the existing
# AutoReach OAuth flow already produces). This is the Phase 3 default.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _Sentinel:
    """Tiny on-disk sidecar marking a token as needing re-auth."""

    invalid: bool
    reason: str
    marked_at: str


class JsonFileTokenStore:
    """
    Stores a single Gmail OAuth credential as a JSON file on disk.

    Compatible with the schema google-auth's `Credentials.to_authorized_user_info()`
    produces. Refreshes via google-auth's `Credentials.refresh()` whenever
    `load()` is called and the token is expired.

    Concurrency
    -----------
    Refreshes are guarded by a per-instance lock so two simultaneous send Jobs
    don't both try to refresh and stomp each other.

    Sidecar: `<token_path>.invalid.json` is a tiny file written by
    `mark_invalid()`; the adapter / cockpit checks this to surface a "reconnect"
    UI without reading the token itself.
    """

    def __init__(
        self,
        *,
        token_path: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        scopes: Optional[list[str]] = None,
    ) -> None:
        self._path = Path(token_path).expanduser()
        self._sidecar = self._path.with_suffix(self._path.suffix + ".invalid.json")
        self._client_id = client_id or os.getenv("GOOGLE_CLIENT_ID") or ""
        self._client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET") or ""
        self._scopes = scopes or [
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.readonly",
        ]
        self._lock = threading.Lock()

    def load(self) -> "object":
        """Return refreshed Credentials, or raise TokenUnavailable / TokenInvalid."""
        if self.is_invalid():
            raise TokenInvalid(self._read_invalid_reason() or "token marked invalid")
        if not self._path.exists():
            raise TokenUnavailable(f"token file not found: {self._path}")

        # Lazy import so non-Gmail usage of the engine doesn't pay the cost.
        try:
            from google.oauth2.credentials import Credentials  # type: ignore
            from google.auth.exceptions import RefreshError  # type: ignore
            from google.auth.transport.requests import Request  # type: ignore
        except Exception as exc:  # pragma: no cover - hard environment issue
            raise TokenUnavailable(f"google-auth not installed: {exc}") from exc

        with self._lock:
            try:
                with self._path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                raise TokenUnavailable(f"could not read {self._path}: {exc}") from exc

            creds = Credentials.from_authorized_user_info(
                _coerce_token_payload(data, self._client_id, self._client_secret),
                scopes=data.get("scopes") or self._scopes,
            )

            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as exc:
                    self.mark_invalid(f"refresh failed: {exc}")
                    raise TokenInvalid(str(exc)) from exc
                # Persist the refreshed token so the next process gets it warm.
                self.save(creds)
            elif creds.expired:
                # No refresh token, can't recover.
                self.mark_invalid("token expired and no refresh_token present")
                raise TokenInvalid("token expired and no refresh_token present")

            return creds

    def save(self, credentials: "object") -> None:
        with self._lock:
            payload = _credentials_to_dict(credentials, fallback_client_id=self._client_id, fallback_client_secret=self._client_secret)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            tmp.replace(self._path)

    def mark_invalid(self, reason: str) -> None:
        sentinel = {
            "invalid": True,
            "reason": reason[:500],
            "marked_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._sidecar.parent.mkdir(parents=True, exist_ok=True)
            with self._sidecar.open("w", encoding="utf-8") as f:
                json.dump(sentinel, f, indent=2)
            logger.warning("Gmail token marked invalid (%s): %s", self._path, reason)
        except OSError as exc:  # pragma: no cover - filesystem errors
            logger.exception("could not write invalid sentinel: %s", exc)

    def clear_invalid(self) -> None:
        """Operator reconnected — call this after writing a fresh token."""
        if self._sidecar.exists():
            self._sidecar.unlink()

    def is_invalid(self) -> bool:
        return self._sidecar.exists()

    def _read_invalid_reason(self) -> Optional[str]:
        if not self._sidecar.exists():
            return None
        try:
            with self._sidecar.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return str(data.get("reason") or "")
        except (OSError, json.JSONDecodeError):
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _coerce_token_payload(
    data: dict,
    client_id: str,
    client_secret: str,
) -> dict:
    """
    Normalize the token JSON to the shape `Credentials.from_authorized_user_info`
    expects. The legacy AutoReach token schema and Google's own token.json
    schema differ slightly; fold them both in.
    """
    out = {
        "token": data.get("token") or data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "token_uri": data.get("token_uri") or "https://oauth2.googleapis.com/token",
        "client_id": data.get("client_id") or client_id,
        "client_secret": data.get("client_secret") or client_secret,
        "scopes": data.get("scopes"),
    }
    return out


def _credentials_to_dict(
    creds: "object",
    *,
    fallback_client_id: str,
    fallback_client_secret: str,
) -> dict:
    """Serialize Credentials back to JSON, defensively across versions."""
    # google-auth provides `to_authorized_user_info()` in modern versions;
    # we fall back to manual serialization if it isn't available.
    if hasattr(creds, "to_authorized_user_info"):
        info = creds.to_authorized_user_info()  # type: ignore[attr-defined]
        if isinstance(info, dict):
            # Don't drop extra fields like `scopes` we want to keep.
            info.setdefault("scopes", list(getattr(creds, "scopes", []) or []))
            info.setdefault("client_id", fallback_client_id)
            info.setdefault("client_secret", fallback_client_secret)
            if getattr(creds, "expiry", None):
                info["expiry"] = creds.expiry.isoformat()  # type: ignore[union-attr]
            return info

    return {
        "token": getattr(creds, "token", None),
        "refresh_token": getattr(creds, "refresh_token", None),
        "token_uri": getattr(creds, "token_uri", "https://oauth2.googleapis.com/token"),
        "client_id": getattr(creds, "client_id", None) or fallback_client_id,
        "client_secret": getattr(creds, "client_secret", None) or fallback_client_secret,
        "scopes": list(getattr(creds, "scopes", []) or []),
        "expiry": (
            creds.expiry.isoformat()  # type: ignore[union-attr]
            if getattr(creds, "expiry", None)
            else None
        ),
    }
