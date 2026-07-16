"""
M9 — MailboxHealthMonitor: warmup ramps + auto-pause on bad metrics.

Two responsibilities:
  1. Warmup: new mailboxes start at a low daily cap and ramp up over ~8 days,
     mimicking organic sending growth so providers don't flag them.
  2. Health: track bounce/spam rates; auto-pause a mailbox that breaches
     thresholds and (optionally) rotate to a reserve.

Metrics come from the event log (EMAIL_SENT, EMAIL_BOUNCED,
EMAIL_SPAM_COMPLAINT), keyed by mailbox_id in the payload, so one sender's
reputation never contaminates another sender's health decision.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from engine.core.types import EventKind
from pydantic import BaseModel, ConfigDict

# Daily send cap by warmup day (index 0 = day 0). After the list, full cap.
WARMUP_RAMP = [10, 15, 25, 40, 60, 80, 100, 150]

BOUNCE_THRESHOLD = 0.05   # 5% → pause
SPAM_THRESHOLD = 0.02     # 2% → pause


class HealthStatus(BaseModel):
    """Structured mailbox health state keyed to a single mailbox_id."""

    model_config = ConfigDict(extra="forbid")

    mailbox_id: str = ""
    sent: int = 0
    bounced: int = 0
    spam_complaints: int = 0
    bounce_rate: float = 0.0
    spam_rate: float = 0.0
    healthy: bool = True
    reason: str = "ok"
    recommended_daily_cap: int = 0
    status: str = "HEALTHY"


class MailboxHealthMonitor:
    def __init__(self, *, store=None, events=None, backend: str = "events") -> None:
        self._store = store
        self._events = events
        self._backend = backend
        self._memory: dict[str, dict[str, int]] = {}

    def recommended_cap(self, warmup_day: int) -> int:
        # Defensive: a legacy/partial mailbox row may carry a null/non-int
        # warmup_day; never let that crash the health check that gates dispatch.
        try:
            warmup_day = int(warmup_day)
        except (TypeError, ValueError):
            warmup_day = 0
        if warmup_day < 0:
            warmup_day = 0
        if warmup_day < len(WARMUP_RAMP):
            return WARMUP_RAMP[warmup_day]
        return 200  # graduated — full cap

    async def log_sent(self, mailbox_id: str) -> None:
        """Record one send in the memory backend."""
        self._memory_row(mailbox_id)["sent"] += 1

    async def log_bounce(self, mailbox_id: str) -> None:
        """Record one bounce in the memory backend."""
        self._memory_row(mailbox_id)["bounced"] += 1

    async def log_spam_complaint(self, mailbox_id: str) -> None:
        """Record one spam complaint in the memory backend."""
        self._memory_row(mailbox_id)["spam_complaints"] += 1

    async def get_health(self, mailbox_id: str) -> HealthStatus:
        """Live mailbox health used by the dispatch router.

        When a store + event log are wired (the production dispatch path), this
        returns the REAL events-based health over a rolling 24h window: durable,
        per-mailbox, and consistent across workers and process restarts. It falls
        back to in-process memory counters only when no event log is available
        (isolated unit tests) — never silently reporting HEALTHY because a fresh
        worker hasn't seen any sends yet.
        """
        if self._store is not None and self._events is not None:
            return self.check_health(mailbox_id)
        row = self._memory_row(mailbox_id)
        return self._build_status(
            mailbox_id=mailbox_id,
            sent=row["sent"],
            bounced=row["bounced"],
            spam_complaints=row["spam_complaints"],
            recommended_daily_cap=0,
        )

    def _memory_row(self, mailbox_id: str) -> dict[str, int]:
        return self._memory.setdefault(
            mailbox_id,
            {"sent": 0, "bounced": 0, "spam_complaints": 0},
        )

    def _event_matches_mailbox(self, ev, mailbox) -> bool:
        payload = dict(ev.payload or {})
        identifiers = {
            payload.get("mailbox_id"),
            payload.get("via_mailbox_id"),
            payload.get("sender_mailbox_id"),
        }
        if mailbox.id in identifiers:
            return True

        # Backward-compatible fallback for older events that recorded address
        # but not mailbox_id. Prefer mailbox_id for all new events.
        addresses = {
            payload.get("mailbox_email"),
            payload.get("via_mailbox_email"),
            payload.get("sender_email"),
            payload.get("from"),
            payload.get("from_email"),
        }
        return mailbox.email_address in addresses

    def check_health(self, mailbox_id: str) -> HealthStatus:
        if self._store is None or self._events is None:
            row = self._memory_row(mailbox_id)
            return self._build_status(
                mailbox_id=mailbox_id,
                sent=row["sent"],
                bounced=row["bounced"],
                spam_complaints=row["spam_complaints"],
                recommended_daily_cap=0,
            )

        mailbox = self._store.get_mailbox(mailbox_id)
        if mailbox is None:
            return HealthStatus(
                mailbox_id=mailbox_id,
                sent=0,
                bounced=0,
                spam_complaints=0,
                bounce_rate=0.0,
                spam_rate=0.0,
                healthy=False,
                reason="mailbox not found",
                recommended_daily_cap=0,
                status="NOT_FOUND",
            )

        # Count sent + bounced + spam complaints for this mailbox over a rolling
        # 24-hour window. Events from other mailboxes are deliberately ignored.
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        sent = bounced = spam_complaints = 0
        for ev in self._events.list_recent(limit=10_000):
            occurred_at = ev.occurred_at
            if occurred_at and occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)
            if occurred_at and occurred_at < since:
                continue
            if not self._event_matches_mailbox(ev, mailbox):
                continue
            if ev.kind == EventKind.EMAIL_SENT:
                sent += 1
            elif ev.kind == EventKind.EMAIL_BOUNCED:
                bounced += 1
            elif ev.kind == EventKind.EMAIL_SPAM_COMPLAINT:
                spam_complaints += 1

        return self._build_status(
            mailbox_id=mailbox_id,
            sent=sent,
            bounced=bounced,
            spam_complaints=spam_complaints,
            recommended_daily_cap=self.recommended_cap(mailbox.warmup_day),
        )

    def _build_status(
        self,
        *,
        mailbox_id: str,
        sent: int,
        bounced: int,
        spam_complaints: int,
        recommended_daily_cap: int,
    ) -> HealthStatus:
        bounce_rate = (bounced / sent) if sent else 0.0
        spam_rate = (spam_complaints / sent) if sent else 0.0
        healthy = bounce_rate < BOUNCE_THRESHOLD and spam_rate < SPAM_THRESHOLD
        if bounce_rate >= BOUNCE_THRESHOLD:
            reason = f"bounce rate {bounce_rate:.1%} exceeds {BOUNCE_THRESHOLD:.0%}"
        elif spam_rate >= SPAM_THRESHOLD:
            reason = f"spam complaint rate {spam_rate:.1%} exceeds {SPAM_THRESHOLD:.0%}"
        else:
            reason = "ok"

        return HealthStatus(
            mailbox_id=mailbox_id, sent=sent, bounced=bounced,
            spam_complaints=spam_complaints,
            bounce_rate=bounce_rate, spam_rate=spam_rate,
            healthy=healthy, reason=reason,
            recommended_daily_cap=recommended_daily_cap,
            status="HEALTHY" if healthy else "PAUSED_SAFETY",
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
