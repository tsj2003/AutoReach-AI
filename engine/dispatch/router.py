"""Deliverability-aware mailbox router."""

from __future__ import annotations

from numbers import Number
from typing import Any, Optional

from engine.dispatch.provider import SMTPProvider
from engine.policies.esp_matcher import EspMatcher
from engine.services.mailbox_health import MailboxHealthMonitor


class _ComparableField:
    """Tiny comparable field for lightweight query filters in tests."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> str:  # type: ignore[override]
        return f"{self.name} == {other!r}"


class MailboxRecord:
    """Minimal mailbox row contract used by the smart router."""

    tenant_id = _ComparableField("tenant_id")


db_session: Any = None


class SmartInboxRouter:
    """Select healthy mailboxes and close the health loop after dispatch."""

    def __init__(
        self,
        *,
        health_monitor: MailboxHealthMonitor,
        provider: Optional[SMTPProvider] = None,
        store: Any = None,
        esp_matcher: Optional[EspMatcher] = None,
    ) -> None:
        self._health_monitor = health_monitor
        self._store = store
        self._provider = provider or SMTPProvider(store=store)
        self._esp_matcher = esp_matcher or EspMatcher()

    @staticmethod
    def _is_eligible(mailbox: Any) -> bool:
        """Cheap pre-filter (status + daily cap) before the costlier health read."""
        status = getattr(mailbox, "status", "active")
        if isinstance(status, str) and status.lower() not in {"active", "warming"}:
            return False
        max_daily = getattr(mailbox, "max_emails_per_day", None)
        sent_today = getattr(mailbox, "emails_sent_today", 0)
        if isinstance(max_daily, Number) and isinstance(sent_today, Number) and sent_today >= max_daily:
            return False
        return True

    def _esp_preferred_order(self, mailboxes: list, recipient_email: Optional[str]) -> list:
        """Order eligible mailboxes so a same-ESP sender is tried first.

        Gmail→Gmail / Outlook→Outlook lands in the primary inbox far more often.
        Ordering (not hard filtering) preserves the health short-circuit and the
        fail-safe: if the same-ESP mailbox is unhealthy we still fall through to
        the next healthy one rather than refusing to send.
        """
        if not recipient_email or len(mailboxes) < 2:
            return mailboxes
        target = self._esp_matcher.detect_provider(recipient_email)
        return sorted(
            mailboxes,
            key=lambda mb: 0
            if self._esp_matcher.normalize_provider(getattr(mb, "provider", None)) == target
            else 1,
        )

    async def get_next_available_mailbox(self, *, tenant_id: str, recipient_email: Optional[str] = None):
        """Return a HEALTHY mailbox, preferring one whose ESP matches the recipient."""

        if self._store is not None:
            mailboxes = list(self._store.list_mailboxes(tenant_id))
        elif db_session is not None:
            mailboxes = db_session.query(MailboxRecord).filter(
                MailboxRecord.tenant_id == tenant_id,
            ).all()
        else:
            return None

        eligible = [mb for mb in mailboxes if self._is_eligible(mb)]
        for mailbox in self._esp_preferred_order(eligible, recipient_email):
            health = await self._health_monitor.get_health(mailbox.id)
            if getattr(health, "status", "") == "HEALTHY":
                return mailbox
        return None

    async def dispatch_email(self, *, mailbox_id: str, payload: dict[str, Any]) -> bool:
        """Send an approved email and update rolling deliverability metrics."""

        sent = await self._provider.send_email(mailbox_id=mailbox_id, payload=payload)
        if sent:
            await self._health_monitor.log_sent(mailbox_id)
            # Increment the persistent daily counter so the cap gate actually
            # bites — otherwise emails_sent_today stays 0 forever and a pilot can
            # over-send and burn the mailbox's domain.
            if self._store is not None and hasattr(self._store, "bump_mailbox_send_count"):
                self._store.bump_mailbox_send_count(mailbox_id)
        return bool(sent)
