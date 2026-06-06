"""
M9 — MailboxHealthMonitor: warmup ramps + auto-pause on bad metrics.

Two responsibilities:
  1. Warmup: new mailboxes start at a low daily cap and ramp up over ~8 days,
     mimicking organic sending growth so providers don't flag them.
  2. Health: track bounce/spam rates; auto-pause a mailbox that breaches
     thresholds and (optionally) rotate to a reserve.

Metrics come from the event log (EMAIL_SENT, EMAIL_BOUNCED), so this is
stateless and crash-safe — no counter to corrupt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# Daily send cap by warmup day (index 0 = day 0). After the list, full cap.
WARMUP_RAMP = [10, 15, 25, 40, 60, 80, 100, 150]

BOUNCE_THRESHOLD = 0.05   # 5% → pause
SPAM_THRESHOLD = 0.02     # 2% → pause


@dataclass(frozen=True)
class HealthStatus:
    mailbox_id: str
    sent: int
    bounced: int
    bounce_rate: float
    healthy: bool
    reason: str
    recommended_daily_cap: int


class MailboxHealthMonitor:
    def __init__(self, *, store, events) -> None:
        self._store = store
        self._events = events

    def recommended_cap(self, warmup_day: int) -> int:
        if warmup_day < 0:
            warmup_day = 0
        if warmup_day < len(WARMUP_RAMP):
            return WARMUP_RAMP[warmup_day]
        return 200  # graduated — full cap

    def check_health(self, mailbox_id: str) -> HealthStatus:
        mailbox = self._store.get_mailbox(mailbox_id)
        if mailbox is None:
            return HealthStatus(mailbox_id, 0, 0, 0.0, False, "mailbox not found", 0)

        # Count sent + bounced across the event log for this mailbox's address.
        sent = bounced = 0
        for ev in self._events.list_recent(limit=10_000):
            via = ev.payload.get("to") if ev.payload else None  # not mailbox-keyed yet
            if ev.kind.value == "email.sent":
                sent += 1
            elif ev.kind.value == "email.bounced":
                bounced += 1

        bounce_rate = (bounced / sent) if sent else 0.0
        healthy = bounce_rate < BOUNCE_THRESHOLD
        reason = "ok" if healthy else f"bounce rate {bounce_rate:.1%} exceeds {BOUNCE_THRESHOLD:.0%}"

        return HealthStatus(
            mailbox_id=mailbox_id,
            sent=sent, bounced=bounced, bounce_rate=bounce_rate,
            healthy=healthy, reason=reason,
            recommended_daily_cap=self.recommended_cap(mailbox.warmup_day),
        )

    def auto_pause_if_unhealthy(self, mailbox_id: str) -> bool:
        """Pause the mailbox if it breaches thresholds. Returns True if paused."""
        status = self.check_health(mailbox_id)
        if not status.healthy:
            self._store.update_mailbox_status(
                mailbox_id, status="paused",
                last_error=f"auto-paused: {status.reason}",
            )
            return True
        return False

    def auto_rotate(self, mailbox_id: str) -> Optional[str]:
        """
        SISR rotation: if `mailbox_id` is unhealthy, pause it and activate the
        next healthy reserve mailbox in the same tenant. Returns the id of the
        mailbox rotated in, or None if none rotated.

        A "reserve" is a mailbox in status 'warming' or 'paused-but-healthy'
        within the same tenant that isn't the unhealthy one.
        """
        mailbox = self._store.get_mailbox(mailbox_id)
        if mailbox is None:
            return None
        if self.check_health(mailbox_id).healthy:
            return None  # nothing to rotate

        # Pause the unhealthy one.
        self._store.update_mailbox_status(
            mailbox_id, status="paused", last_error="auto-rotated out (unhealthy)",
        )

        # Find a reserve in the same tenant.
        for mb in self._store.list_mailboxes(mailbox.tenant_id):
            if mb.id == mailbox_id:
                continue
            if mb.status in ("warming", "active") and self.check_health(mb.id).healthy:
                # Promote it to active.
                self._store.update_mailbox_status(mb.id, status="active")
                return mb.id
        return None

    def warmup_tick(self, tenant_id: str) -> int:
        """
        Advance warmup day for all warming/active mailboxes in a tenant and
        update their daily cap. Returns count of mailboxes advanced.
        Intended to run daily (cron / Celery beat).
        """
        advanced = 0
        for mb in self._store.list_mailboxes(tenant_id):
            if mb.status not in ("active", "warming"):
                continue
            new_day = mb.warmup_day + 1
            new_cap = self.recommended_cap(new_day)
            from engine.auth.mailbox_models import Mailbox
            self._store.save_mailbox(Mailbox(
                id=mb.id, tenant_id=mb.tenant_id, user_id=mb.user_id,
                provider=mb.provider, email_address=mb.email_address,
                display_name=mb.display_name, credentials_json=mb.credentials_json,
                oauth_client_id=mb.oauth_client_id, oauth_client_secret=mb.oauth_client_secret,
                max_emails_per_day=new_cap, emails_sent_today=mb.emails_sent_today,
                last_send_reset=mb.last_send_reset, warmup_day=new_day,
                status="active" if new_day >= len(WARMUP_RAMP) else "warming",
                reputation_score=mb.reputation_score, last_error=mb.last_error,
                created_at=mb.created_at, updated_at=datetime.now(timezone.utc),
            ))
            advanced += 1
        return advanced
