"""
M5 — SendRateLimiter: per-engagement daily send caps + sending windows.

This is the deliverability guardrail. Without it a single campaign can torch
its sender reputation in an afternoon. It also forms the basis of commercial
tier enforcement (plan_limits).

Checks performed by `can_send()`:
    1. Engagement daily send count < engagement.max_emails_per_day
    2. Current UTC hour within [sending_window_start, sending_window_end)
    3. (future) per-mailbox cap — added in M4/M9 when mailboxes exist

Daily counting is done by reading EMAIL_SENT events since UTC midnight, so it's
stateless and crash-safe (no counter to corrupt).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Optional

from engine.core.protocols import EventSink, Store


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str
    retry_after_seconds: Optional[int] = None


# Engine-level defaults (overridable per engagement via metadata).
DEFAULT_MAX_EMAILS_PER_DAY = 200
DEFAULT_WINDOW_START_HOUR = 0   # 0 = no window restriction by default
DEFAULT_WINDOW_END_HOUR = 24


class SendRateLimiter:
    def __init__(self, *, store: Store, events: EventSink) -> None:
        self._store = store
        self._events = events

    def _sent_today(self, engagement_id: str) -> int:
        """Count EMAIL_SENT events since UTC midnight for this engagement."""
        midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        count = 0
        for ev in self._events.list_recent(engagement_id=engagement_id, kind="email.sent", limit=10_000):
            if ev.occurred_at and ev.occurred_at >= midnight:
                count += 1
        return count

    def can_send(self, engagement_id: str) -> RateLimitDecision:
        eng = self._store.get_engagement(engagement_id)
        if eng is None:
            return RateLimitDecision(False, "engagement not found")

        meta = dict(eng.metadata or {})
        max_per_day = int(meta.get("max_emails_per_day", DEFAULT_MAX_EMAILS_PER_DAY))
        window_start = int(meta.get("sending_window_start", DEFAULT_WINDOW_START_HOUR))
        window_end = int(meta.get("sending_window_end", DEFAULT_WINDOW_END_HOUR))

        # 1. Daily cap.
        sent = self._sent_today(engagement_id)
        if sent >= max_per_day:
            # Retry after next UTC midnight.
            now = datetime.now(timezone.utc)
            tomorrow = (now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400)
            return RateLimitDecision(
                False,
                f"daily send cap reached ({sent}/{max_per_day})",
                retry_after_seconds=int(tomorrow - now.timestamp()),
            )

        # 2. Sending window (UTC hours).
        if window_start != 0 or window_end != 24:
            hour = datetime.now(timezone.utc).hour
            in_window = window_start <= hour < window_end
            if not in_window:
                # Compute seconds until window opens.
                now = datetime.now(timezone.utc)
                next_open = now.replace(hour=window_start % 24, minute=0, second=0, microsecond=0)
                if hour >= window_end:
                    # window is later today→tomorrow
                    secs = int((next_open.timestamp() + 86400) - now.timestamp())
                else:
                    secs = int(next_open.timestamp() - now.timestamp())
                return RateLimitDecision(
                    False,
                    f"outside sending window ({window_start}:00–{window_end}:00 UTC)",
                    retry_after_seconds=max(60, secs),
                )

        return RateLimitDecision(True, "ok")
