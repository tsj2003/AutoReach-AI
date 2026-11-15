"""Auth domain models — Tenant, User, CurrentUser."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str
    plan: str = "free"          # free | starter | pro | enterprise
    trial_ends_at: datetime | None = None  # set during a free trial; None once paid/expired
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class User:
    id: str
    tenant_id: str
    email: str
    password_hash: str
    full_name: str = ""
    role: str = "member"        # owner | admin | member
    is_active: bool = True
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class CurrentUser:
    """Decoded JWT principal — injected into every authenticated FastAPI handler."""

    user_id: str
    tenant_id: str
    email: str
    role: str
    plan: str                   # tenant's plan, denormalized for quick tier checks

    def is_owner(self) -> bool:
        return self.role == "owner"

    def is_admin_or_above(self) -> bool:
        return self.role in ("owner", "admin")
