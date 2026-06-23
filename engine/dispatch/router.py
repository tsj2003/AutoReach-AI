"""Deliverability-aware mailbox router."""

from __future__ import annotations

from numbers import Number
from typing import Any, Optional

from engine.dispatch.provider import SMTPProvider
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
    ) -> None:
        self._health_monitor = health_monitor
        self._store = store
        self._provider = provider or SMTPProvider(store=store)

    async def get_next_available_mailbox(self, *, tenant_id: str):
        """Return the first mailbox whose live health status is strictly HEALTHY."""

        if self._store is not None:
            mailboxes = list(self._store.list_mailboxes(tenant_id))
        elif db_session is not None:
            mailboxes = db_session.query(MailboxRecord).filter(
                MailboxRecord.tenant_id == tenant_id,
            ).all()
        else:
            return None

        for mailbox in mailboxes:
            mailbox_status = getattr(mailbox, "status", "active")
            if isinstance(mailbox_status, str) and mailbox_status.lower() not in {"active", "warming"}:
                continue
            max_daily = getattr(mailbox, "max_emails_per_day", None)
            sent_today = getattr(mailbox, "emails_sent_today", 0)
            if isinstance(max_daily, Number) and isinstance(sent_today, Number) and sent_today >= max_daily:
                continue
            health = await self._health_monitor.get_health(mailbox.id)
            if getattr(health, "status", "") == "HEALTHY":
                return mailbox
        return None

    async def dispatch_email(self, *, mailbox_id: str, payload: dict[str, Any]) -> bool:
        """Send an approved email and update rolling deliverability metrics."""

        sent = await self._provider.send_email(mailbox_id=mailbox_id, payload=payload)
        if sent:
            await self._health_monitor.log_sent(mailbox_id)
        return bool(sent)
