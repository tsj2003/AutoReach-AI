"""Mailbox domain model (M4) — a connected email account."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Mailbox:
    id: str
    tenant_id: str
    email_address: str
    provider: str = "gmail"        # gmail | outlook | smtp
    user_id: Optional[str] = None
    display_name: Optional[str] = None
    credentials_json: Optional[dict] = None     # authorized-user-info blob
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None
    max_emails_per_day: int = 50
    emails_sent_today: int = 0
    last_send_reset: Optional[datetime] = None
    warmup_day: int = 0
    status: str = "active"          # active | paused | revoked | warming
    reputation_score: int = 100
    last_error: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
