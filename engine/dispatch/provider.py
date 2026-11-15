"""Outbound email provider abstraction.

The provider is intentionally thin: mailbox selection lives in
``SmartInboxRouter`` and provider execution lives here. For production Gmail
mailboxes, this wraps the existing ``RealGmailSendAdapter`` with a per-mailbox
``DbTokenStore`` so the dispatch layer uses the same audited adapter path as
the runtime.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Callable, Optional

from engine.adapters.db_token_store import DbTokenStore
from engine.adapters.email_gmail_real import GmailMailer, RealGmailSendAdapter
from engine.adapters.gmail_token_store import MISSING_REFRESH_TOKEN_ERROR
from engine.debug_agent import agent_debug
from engine.core.types import Job, JobKind
from engine.runtime.contexts import DefaultAdapterContext

logger = logging.getLogger(__name__)


class SMTPProvider:
    """Async provider surface for health-gated email dispatch."""

    def __init__(
        self,
        *,
        store: Any = None,
        events: Any = None,
        ledger: Any = None,
        gmail_adapter_factory: Optional[Callable[..., RealGmailSendAdapter]] = None,
        dry_run: Optional[bool] = None,
    ) -> None:
        self._store = store
        self._events = events
        self._ledger = ledger
        self._gmail_adapter_factory = gmail_adapter_factory or GmailMailer
        self._dry_run = dry_run

    async def send_email(self, *, mailbox_id: str, payload: dict[str, Any]) -> bool:
        """Send one email payload through the selected mailbox.

        When no storage dependencies are injected, this remains a harmless
        in-memory success path for existing contract tests. Production callers
        inject store/events/ledger and get the real Gmail adapter path.
        """

        if self._store is None or self._events is None or self._ledger is None:
            return True

        mailbox = self._store.get_mailbox(mailbox_id)
        if mailbox is None:
            logger.warning("dispatch skipped: mailbox not found mailbox_id=%s", mailbox_id)
            return False
        if getattr(mailbox, "status", "") == "revoked":
            logger.warning("dispatch skipped: mailbox revoked mailbox_id=%s", mailbox_id)
            return False

        normalized = self._normalize_payload(payload)
        if not normalized.get("to_email"):
            logger.warning("dispatch skipped: missing recipient mailbox_id=%s", mailbox_id)
            return False

        dry_run = self._dry_run
        if dry_run is None:
            dry_run = os.getenv("AUTOREACH_GMAIL_DRY_RUN", "").strip().lower() in (
                "1", "true", "yes", "on",
            )

        adapter = self._gmail_adapter_factory(
            sender_email=getattr(mailbox, "email_address", ""),
            token_store=DbTokenStore(store=self._store, mailbox_id=mailbox_id),
            dry_run=dry_run,
        )
        job = Job(
            id=str(normalized.get("job_id") or f"dispatch_{secrets.token_hex(8)}"),
            engagement_id=str(
                normalized.get("engagement_id")
                or normalized.get("campaign_id")
                or ""
            ),
            agent_id=str(normalized.get("agent_id") or "hitl_dispatch"),
            kind=JobKind.EMAIL_SEND,
            payload=normalized,
            prospect_id=normalized.get("prospect_id"),
        )
        context = DefaultAdapterContext(self._store, self._events, self._ledger)

        try:
            result = adapter.execute(job, context=context)
        except Exception as exc:
            logger.exception("dispatch adapter raised mailbox_id=%s", mailbox_id)
            detail = str(exc or "")
            if "refresh_token" in detail.lower():
                reason = MISSING_REFRESH_TOKEN_ERROR
            else:
                reason = f"gmail send failed ({type(exc).__name__})"
            agent_debug(
                "C",
                "provider.py:send_email",
                "dispatch adapter raised",
                {
                    "mailbox_id": mailbox_id,
                    "exc_type": type(exc).__name__,
                    "refresh_token_in_error": "refresh_token" in detail.lower(),
                    "reason": reason[:160],
                },
            )
            self._record_mailbox_error(mailbox_id, reason)
            return False

        if not result.succeeded:
            logger.warning(
                "dispatch failed mailbox_id=%s error=%s",
                mailbox_id,
                result.error,
            )
            agent_debug(
                "C",
                "provider.py:send_email",
                "dispatch failed",
                {
                    "mailbox_id": mailbox_id,
                    "error": str(result.error or "")[:160],
                    "refresh_token_in_error": "refresh_token" in str(result.error or "").lower(),
                },
            )
            self._record_mailbox_error(
                mailbox_id, result.error or "email dispatch failed through selected mailbox"
            )
            return False

        output = dict(result.output or {})
        return bool(output.get("sent", True)) and not bool(output.get("dry_run", False))


    def _record_mailbox_error(self, mailbox_id: str, reason: str) -> None:
        if self._store is None or not hasattr(self._store, "update_mailbox_status"):
            return
        mailbox = self._store.get_mailbox(mailbox_id)
        if mailbox is None:
            return
        status = getattr(mailbox, "status", None) or "active"
        self._store.update_mailbox_status(
            mailbox_id, status=status, last_error=(reason or "gmail send failed")[:500]
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload or {})
        if "to_email" not in normalized and "to" in normalized:
            normalized["to_email"] = normalized.get("to")
        if "body_text" not in normalized and "body" in normalized:
            normalized["body_text"] = normalized.get("body")
        return normalized
