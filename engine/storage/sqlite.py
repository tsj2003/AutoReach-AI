"""
SQLite (and Postgres) storage for the engine, via SQLAlchemy Core.
Multi-tenant from M1: every table has an optional `tenant_id` column.
Single-operator usage passes `tenant_id=None` and all queries still work.
"""

from __future__ import annotations

import json as _json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)
from sqlalchemy.engine import Connection

from engine.auth.models import Tenant, User
from engine.core.types import (
    Agent,
    CostEntry,
    Engagement,
    Event,
    EventKind,
    Job,
    JobKind,
    Meeting,
    Prospect,
    Reply,
)

# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

metadata = MetaData()

# ── Auth tables (M1) ─────────────────────────────────────────────────────────

tenants_table = Table(
    "tenants",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("plan", String, nullable=False, default="free"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

users_table = Table(
    "users",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("email", String, nullable=False, index=True),
    Column("password_hash", String, nullable=False),
    Column("full_name", String, nullable=False, default=""),
    Column("role", String, nullable=False, default="member"),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# ── Engine tables ─────────────────────────────────────────────────────────────

engagements_table = Table(
    "engagements",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=True, index=True),   # M1: nullable for backward compat
    Column("customer_name", String, nullable=False),
    Column("offer", Text, nullable=False),
    Column("icp_description", Text, nullable=False),
    Column("icp_filters", JSON, nullable=False, default=dict),
    Column("booking_url", String, nullable=True),
    Column("monthly_meeting_target", Integer, nullable=True),
    Column("price_per_outcome_cents", Integer, nullable=True),
    Column("monthly_budget_cents", Integer, nullable=True),
    Column("status", String, nullable=False, default="active"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("metadata_json", JSON, nullable=False, default=dict),
)


prospects_table = Table(
    "prospects",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=True, index=True),
    Column("engagement_id", String, nullable=False, index=True),
    Column("email", String, nullable=True, index=True),
    Column("full_name", String, nullable=True),
    Column("company", String, nullable=True),
    Column("title", String, nullable=True),
    Column("raw", JSON, nullable=False, default=dict),
    Column("research", JSON, nullable=False, default=dict),
    Column("status", String, nullable=False, default="new", index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


agents_table = Table(
    "agents",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=True, index=True),
    Column("engagement_id", String, nullable=False, index=True),
    Column("runner_kind", String, nullable=False),
    Column("config", JSON, nullable=False, default=dict),
    Column("status", String, nullable=False, default="active"),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


jobs_table = Table(
    "jobs",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=True, index=True),
    Column("engagement_id", String, nullable=False, index=True),
    Column("agent_id", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("payload", JSON, nullable=False, default=dict),
    Column("state", String, nullable=False, default="pending", index=True),
    Column("prospect_id", String, nullable=True),
    Column("parent_job_id", String, nullable=True),
    Column("requires_approval", Boolean, nullable=False, default=False),
    Column("scheduled_for", DateTime(timezone=True), nullable=False),
    Column("not_before", DateTime(timezone=True), nullable=True),
    Column("attempt", Integer, nullable=False, default=0),
    Column("max_attempts", Integer, nullable=False, default=3),
    Column("last_error", Text, nullable=True),
    Column("result", JSON, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


events_table = Table(
    "events",
    metadata,
    Column("id", String, primary_key=True),
    Column("kind", String, nullable=False, index=True),
    Column("engagement_id", String, nullable=True, index=True),
    Column("agent_id", String, nullable=True),
    Column("job_id", String, nullable=True, index=True),
    Column("prospect_id", String, nullable=True, index=True),
    Column("payload", JSON, nullable=False, default=dict),
    Column("occurred_at", DateTime(timezone=True), nullable=False, index=True),
)


cost_entries_table = Table(
    "cost_entries",
    metadata,
    Column("id", String, primary_key=True),
    Column("engagement_id", String, nullable=False, index=True),
    Column("job_id", String, nullable=True),
    Column("category", String, nullable=False, index=True),
    Column("amount_cents", Integer, nullable=False),
    Column("metadata_json", JSON, nullable=False, default=dict),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)


orphaned_replies_table = Table(
    "orphaned_replies",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=True, index=True),
    Column("from_email", String, nullable=False, index=True),
    Column("from_name", String, nullable=True),
    Column("subject", String, nullable=True),
    Column("snippet", Text, nullable=True),
    Column("external_message_id", String, nullable=True, index=True),
    Column("attached_prospect_id", String, nullable=True),
    Column("status", String, nullable=False, default="unmatched", index=True),
    Column("received_at", DateTime(timezone=True), nullable=False),
)


mailboxes_table = Table(
    "mailboxes",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("user_id", String, nullable=True),
    Column("provider", String, nullable=False, default="gmail"),
    Column("email_address", String, nullable=False, index=True),
    Column("display_name", String, nullable=True),
    # OAuth credentials (stored as JSON authorized-user-info blob)
    Column("credentials_json", JSON, nullable=True),
    Column("oauth_client_id", String, nullable=True),
    Column("oauth_client_secret", String, nullable=True),
    # Rate limits / warmup (M5/M9)
    Column("max_emails_per_day", Integer, nullable=False, default=50),
    Column("emails_sent_today", Integer, nullable=False, default=0),
    Column("last_send_reset", DateTime(timezone=True), nullable=True),
    Column("warmup_day", Integer, nullable=False, default=0),
    # Health
    Column("status", String, nullable=False, default="active", index=True),  # active|paused|revoked|warming
    Column("reputation_score", Integer, nullable=False, default=100),
    Column("last_error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


replies_table = Table(
    "replies",
    metadata,
    Column("id", String, primary_key=True),
    Column("engagement_id", String, nullable=False, index=True),
    Column("prospect_id", String, nullable=False, index=True),
    Column("job_id", String, nullable=True),
    Column("snippet", Text, nullable=False),
    Column("classification", String, nullable=False, default="objection"),
    Column("suggested_reply", Text, nullable=False, default=""),
    Column("status", String, nullable=False, default="pending", index=True),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("external_message_id", String, nullable=True, index=True),
)


meetings_table = Table(
    "meetings",
    metadata,
    Column("id", String, primary_key=True),
    Column("engagement_id", String, nullable=False, index=True),
    Column("prospect_id", String, nullable=False, index=True),
    Column("reply_id", String, nullable=True),
    Column("scheduled_for", DateTime(timezone=True), nullable=False),
    Column("status", String, nullable=False, default="booked", index=True),
    Column("booked_at", DateTime(timezone=True), nullable=False),
    Column("notes", Text, nullable=False, default=""),
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite drops tzinfo; reattach UTC for consistency with type contracts."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _coerce_json(value: Any) -> dict:
    """Tolerate strings if a column was previously stored as TEXT."""
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            return _json.loads(value)
        except _json.JSONDecodeError:
            return {}
    return dict(value)


def _row_to_engagement(row: Any) -> Engagement:
    return Engagement(
        id=row.id,
        customer_name=row.customer_name,
        offer=row.offer,
        icp_description=row.icp_description,
        icp_filters=_coerce_json(row.icp_filters),
        booking_url=row.booking_url,
        monthly_meeting_target=row.monthly_meeting_target,
        price_per_outcome_cents=row.price_per_outcome_cents,
        monthly_budget_cents=row.monthly_budget_cents,
        status=row.status,
        created_at=_ensure_utc(row.created_at),  # type: ignore[arg-type]
        metadata=_coerce_json(row.metadata_json),
    )


def _row_to_prospect(row: Any) -> Prospect:
    return Prospect(
        id=row.id,
        engagement_id=row.engagement_id,
        email=row.email,
        full_name=row.full_name,
        company=row.company,
        title=row.title,
        raw=_coerce_json(row.raw),
        research=_coerce_json(row.research),
        status=row.status,
        created_at=_ensure_utc(row.created_at),  # type: ignore[arg-type]
    )


def _row_to_agent(row: Any) -> Agent:
    return Agent(
        id=row.id,
        engagement_id=row.engagement_id,
        runner_kind=row.runner_kind,
        config=_coerce_json(row.config),
        status=row.status,
        created_at=_ensure_utc(row.created_at),  # type: ignore[arg-type]
    )


def _row_to_job(row: Any) -> Job:
    return Job(
        id=row.id,
        engagement_id=row.engagement_id,
        agent_id=row.agent_id,
        kind=JobKind(row.kind),
        payload=_coerce_json(row.payload),
        state=row.state,
        prospect_id=row.prospect_id,
        parent_job_id=row.parent_job_id,
        requires_approval=bool(row.requires_approval),
        scheduled_for=_ensure_utc(row.scheduled_for),  # type: ignore[arg-type]
        not_before=_ensure_utc(row.not_before),
        attempt=row.attempt,
        max_attempts=row.max_attempts,
        last_error=row.last_error,
        result=_coerce_json(row.result),
        created_at=_ensure_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_ensure_utc(row.updated_at),  # type: ignore[arg-type]
    )


def _row_to_event(row: Any) -> Event:
    return Event(
        id=row.id,
        kind=EventKind(row.kind),
        engagement_id=row.engagement_id,
        agent_id=row.agent_id,
        job_id=row.job_id,
        prospect_id=row.prospect_id,
        payload=_coerce_json(row.payload),
        occurred_at=_ensure_utc(row.occurred_at),  # type: ignore[arg-type]
    )


def _row_to_cost(row: Any) -> CostEntry:
    return CostEntry(
        id=row.id,
        engagement_id=row.engagement_id,
        job_id=row.job_id,
        category=row.category,
        amount_cents=row.amount_cents,
        metadata=_coerce_json(row.metadata_json),
        occurred_at=_ensure_utc(row.occurred_at),  # type: ignore[arg-type]
    )


def _row_to_reply(row: Any) -> Reply:
    return Reply(
        id=row.id,
        engagement_id=row.engagement_id,
        prospect_id=row.prospect_id,
        job_id=row.job_id,
        snippet=row.snippet,
        classification=row.classification,
        suggested_reply=row.suggested_reply,
        status=row.status,
        received_at=_ensure_utc(row.received_at),  # type: ignore[arg-type]
        external_message_id=row.external_message_id,
    )


def _row_to_meeting(row: Any) -> Meeting:
    return Meeting(
        id=row.id,
        engagement_id=row.engagement_id,
        prospect_id=row.prospect_id,
        reply_id=row.reply_id,
        scheduled_for=_ensure_utc(row.scheduled_for),  # type: ignore[arg-type]
        status=row.status,
        booked_at=_ensure_utc(row.booked_at),  # type: ignore[arg-type]
        notes=row.notes,
    )


def _row_to_tenant(row: Any) -> Tenant:
    return Tenant(
        id=row.id,
        name=row.name,
        plan=row.plan,
        created_at=_ensure_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_ensure_utc(row.updated_at),  # type: ignore[arg-type]
    )


def _row_to_user(row: Any) -> User:
    return User(
        id=row.id,
        tenant_id=row.tenant_id,
        email=row.email,
        password_hash=row.password_hash,
        full_name=row.full_name or "",
        role=row.role,
        is_active=bool(row.is_active),
        created_at=_ensure_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_ensure_utc(row.updated_at),  # type: ignore[arg-type]
    )


def _row_to_mailbox(row: Any) -> "Mailbox":
    from engine.auth.mailbox_models import Mailbox
    return Mailbox(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        provider=row.provider,
        email_address=row.email_address,
        display_name=row.display_name,
        credentials_json=_coerce_json(row.credentials_json) if row.credentials_json else None,
        oauth_client_id=row.oauth_client_id,
        oauth_client_secret=row.oauth_client_secret,
        max_emails_per_day=row.max_emails_per_day,
        emails_sent_today=row.emails_sent_today,
        last_send_reset=_ensure_utc(row.last_send_reset),
        warmup_day=row.warmup_day,
        status=row.status,
        reputation_score=row.reputation_score,
        last_error=row.last_error,
        created_at=_ensure_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_ensure_utc(row.updated_at),  # type: ignore[arg-type]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Connection management
# ─────────────────────────────────────────────────────────────────────────────


class _EngineHolder:
    """
    Wraps a SQLAlchemy Engine so the three storage classes can share it.

    Each operation opens a transactional connection (`begin()`); we don't
    keep long-lived connections around. Concurrency safety comes from
    SQLite's WAL mode + serialized writes, or from Postgres natively
    once we migrate.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def conn(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection


def open_storage(url: str = "sqlite:///autoreach_engine.db") -> tuple[
    "SqliteStore",
    "SqliteEventSink",
    "SqliteCostLedger",
]:
    """
    Open a SQLite or Postgres URL and return the three storage backends
    sharing one Engine.

    Postgres
    --------
    * `postgres://` is rewritten to `postgresql://` (Render/Heroku quirk;
      SQLAlchemy 2.x requires the latter).
    * Connection pooling is enabled (pool_pre_ping handles stale connections).

    SQLite
    ------
    * WAL mode for safer concurrent reads.
    * Same Table definitions — zero schema changes between the two.
    """
    # Normalize the Render/Heroku-style postgres scheme.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    is_sqlite = url.startswith("sqlite")

    if is_sqlite:
        engine = create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False},
        )
    else:
        # Postgres (or other server DB): connection pooling.
        engine = create_engine(
            url,
            future=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=300,
            pool_pre_ping=True,
        )

    metadata.create_all(engine)
    if is_sqlite:
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
    holder = _EngineHolder(engine)
    return (
        SqliteStore(holder),
        SqliteEventSink(holder),
        SqliteCostLedger(holder),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Store
# ─────────────────────────────────────────────────────────────────────────────


class SqliteStore:
    """Concrete `engine.core.protocols.Store` backed by SQLite/Postgres."""

    def __init__(self, holder: _EngineHolder) -> None:
        self._holder = holder

    # ── Tenants (M1) ──────────────────────────────────────────────────────

    def save_tenant(self, tenant: Tenant) -> None:
        values = {
            "id": tenant.id, "name": tenant.name, "plan": tenant.plan,
            "created_at": tenant.created_at, "updated_at": tenant.updated_at,
        }
        with self._holder.conn() as c:
            existing = c.execute(select(tenants_table.c.id).where(tenants_table.c.id == tenant.id)).first()
            if existing:
                c.execute(tenants_table.update().where(tenants_table.c.id == tenant.id).values(**values))
            else:
                c.execute(tenants_table.insert().values(**values))

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        with self._holder.conn() as c:
            row = c.execute(select(tenants_table).where(tenants_table.c.id == tenant_id)).first()
            return _row_to_tenant(row) if row else None

    # ── Users (M1) ────────────────────────────────────────────────────────

    def save_user(self, user: User) -> None:
        values = {
            "id": user.id, "tenant_id": user.tenant_id, "email": user.email,
            "password_hash": user.password_hash, "full_name": user.full_name,
            "role": user.role, "is_active": user.is_active,
            "created_at": user.created_at, "updated_at": user.updated_at,
        }
        with self._holder.conn() as c:
            existing = c.execute(select(users_table.c.id).where(users_table.c.id == user.id)).first()
            if existing:
                c.execute(users_table.update().where(users_table.c.id == user.id).values(**values))
            else:
                c.execute(users_table.insert().values(**values))

    def get_user(self, user_id: str) -> Optional[User]:
        with self._holder.conn() as c:
            row = c.execute(select(users_table).where(users_table.c.id == user_id)).first()
            return _row_to_user(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self._holder.conn() as c:
            row = c.execute(select(users_table).where(users_table.c.email == email.lower())).first()
            return _row_to_user(row) if row else None

    def list_users_for_tenant(self, tenant_id: str) -> Iterable[User]:
        with self._holder.conn() as c:
            rows = c.execute(select(users_table).where(users_table.c.tenant_id == tenant_id)).all()
            return [_row_to_user(r) for r in rows]

    # ── Mailboxes (M4) ────────────────────────────────────────────────────

    def save_mailbox(self, mailbox) -> None:
        values = {
            "id": mailbox.id, "tenant_id": mailbox.tenant_id, "user_id": mailbox.user_id,
            "provider": mailbox.provider, "email_address": mailbox.email_address,
            "display_name": mailbox.display_name,
            "credentials_json": dict(mailbox.credentials_json) if mailbox.credentials_json else None,
            "oauth_client_id": mailbox.oauth_client_id,
            "oauth_client_secret": mailbox.oauth_client_secret,
            "max_emails_per_day": mailbox.max_emails_per_day,
            "emails_sent_today": mailbox.emails_sent_today,
            "last_send_reset": mailbox.last_send_reset,
            "warmup_day": mailbox.warmup_day, "status": mailbox.status,
            "reputation_score": mailbox.reputation_score, "last_error": mailbox.last_error,
            "created_at": mailbox.created_at, "updated_at": mailbox.updated_at,
        }
        with self._holder.conn() as c:
            existing = c.execute(select(mailboxes_table.c.id).where(mailboxes_table.c.id == mailbox.id)).first()
            if existing:
                c.execute(mailboxes_table.update().where(mailboxes_table.c.id == mailbox.id).values(**values))
            else:
                c.execute(mailboxes_table.insert().values(**values))

    def get_mailbox(self, mailbox_id: str):
        with self._holder.conn() as c:
            row = c.execute(select(mailboxes_table).where(mailboxes_table.c.id == mailbox_id)).first()
            return _row_to_mailbox(row) if row else None

    def list_mailboxes(self, tenant_id: str, *, status: Optional[str] = None):
        stmt = select(mailboxes_table).where(mailboxes_table.c.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(mailboxes_table.c.status == status)
        with self._holder.conn() as c:
            return [_row_to_mailbox(r) for r in c.execute(stmt).all()]

    def update_mailbox_credentials(self, mailbox_id: str, *, credentials_json: dict) -> None:
        with self._holder.conn() as c:
            c.execute(mailboxes_table.update().where(mailboxes_table.c.id == mailbox_id).values(
                credentials_json=dict(credentials_json),
                updated_at=datetime.now(timezone.utc),
            ))

    def update_mailbox_status(self, mailbox_id: str, *, status: str, last_error: Optional[str] = None) -> None:
        vals = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if last_error is not None:
            vals["last_error"] = last_error
        with self._holder.conn() as c:
            c.execute(mailboxes_table.update().where(mailboxes_table.c.id == mailbox_id).values(**vals))

    # ── Orphaned replies (M7) ─────────────────────────────────────────────

    def save_orphaned_reply(self, *, id: str, tenant_id: Optional[str], from_email: str,
                            from_name: Optional[str], subject: Optional[str],
                            snippet: Optional[str], external_message_id: Optional[str],
                            status: str = "unmatched") -> None:
        from datetime import datetime as _dt, timezone as _tz
        values = {
            "id": id, "tenant_id": tenant_id, "from_email": from_email,
            "from_name": from_name, "subject": subject, "snippet": snippet,
            "external_message_id": external_message_id, "attached_prospect_id": None,
            "status": status, "received_at": _dt.now(_tz.utc),
        }
        with self._holder.conn() as c:
            existing = c.execute(select(orphaned_replies_table.c.id).where(
                orphaned_replies_table.c.id == id)).first()
            if existing:
                c.execute(orphaned_replies_table.update().where(
                    orphaned_replies_table.c.id == id).values(**values))
            else:
                c.execute(orphaned_replies_table.insert().values(**values))

    def get_orphaned_by_external_id(self, external_message_id: str):
        with self._holder.conn() as c:
            row = c.execute(select(orphaned_replies_table).where(
                orphaned_replies_table.c.external_message_id == external_message_id)).first()
            return dict(row._mapping) if row else None

    def list_orphaned_replies(self, tenant_id: Optional[str] = None, *, status: str = "unmatched", limit: int = 100):
        stmt = select(orphaned_replies_table).where(orphaned_replies_table.c.status == status)
        if tenant_id is not None:
            stmt = stmt.where(orphaned_replies_table.c.tenant_id == tenant_id)
        stmt = stmt.order_by(orphaned_replies_table.c.received_at.desc()).limit(limit)
        with self._holder.conn() as c:
            return [dict(r._mapping) for r in c.execute(stmt).all()]

    def attach_orphaned_reply(self, orphan_id: str, prospect_id: str) -> bool:
        with self._holder.conn() as c:
            existing = c.execute(select(orphaned_replies_table.c.id).where(
                orphaned_replies_table.c.id == orphan_id)).first()
            if not existing:
                return False
            c.execute(orphaned_replies_table.update().where(
                orphaned_replies_table.c.id == orphan_id).values(
                attached_prospect_id=prospect_id, status="attached"))
            return True

    # ── Engagements ───────────────────────────────────────────────────────

    def save_engagement(self, engagement: Engagement, *, tenant_id: Optional[str] = None) -> None:
        values = {
            "id": engagement.id,
            "tenant_id": tenant_id or getattr(engagement, "tenant_id", None),
            "customer_name": engagement.customer_name,
            "offer": engagement.offer,
            "icp_description": engagement.icp_description,
            "icp_filters": dict(engagement.icp_filters),
            "booking_url": engagement.booking_url,
            "monthly_meeting_target": engagement.monthly_meeting_target,
            "price_per_outcome_cents": engagement.price_per_outcome_cents,
            "monthly_budget_cents": engagement.monthly_budget_cents,
            "status": engagement.status,
            "created_at": engagement.created_at,
            "metadata_json": dict(engagement.metadata),
        }
        with self._holder.conn() as c:
            existing = c.execute(
                select(engagements_table.c.id).where(engagements_table.c.id == engagement.id)
            ).first()
            if existing:
                c.execute(engagements_table.update().where(engagements_table.c.id == engagement.id).values(**values))
            else:
                c.execute(engagements_table.insert().values(**values))

    def get_engagement(self, engagement_id: str, *, tenant_id: Optional[str] = None) -> Optional[Engagement]:
        with self._holder.conn() as c:
            stmt = select(engagements_table).where(engagements_table.c.id == engagement_id)
            if tenant_id is not None:
                stmt = stmt.where(engagements_table.c.tenant_id == tenant_id)
            row = c.execute(stmt).first()
            return _row_to_engagement(row) if row else None

    def list_engagements(self, *, status: Optional[str] = None, tenant_id: Optional[str] = None) -> Iterable[Engagement]:
        stmt = select(engagements_table)
        if tenant_id is not None:
            stmt = stmt.where(engagements_table.c.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(engagements_table.c.status == status)
        with self._holder.conn() as c:
            return [_row_to_engagement(r) for r in c.execute(stmt).all()]

    # ── Agents ────────────────────────────────────────────────────────────

    def save_agent(self, agent: Agent, *, tenant_id: Optional[str] = None) -> None:
        values = {
            "id": agent.id,
            "tenant_id": tenant_id,
            "engagement_id": agent.engagement_id,
            "runner_kind": agent.runner_kind,
            "config": dict(agent.config),
            "status": agent.status,
            "created_at": agent.created_at,
        }
        with self._holder.conn() as c:
            existing = c.execute(select(agents_table.c.id).where(agents_table.c.id == agent.id)).first()
            if existing:
                c.execute(agents_table.update().where(agents_table.c.id == agent.id).values(**values))
            else:
                c.execute(agents_table.insert().values(**values))

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        with self._holder.conn() as c:
            row = c.execute(select(agents_table).where(agents_table.c.id == agent_id)).first()
            return _row_to_agent(row) if row else None

    def list_agents(self, engagement_id: str) -> Iterable[Agent]:
        with self._holder.conn() as c:
            return [_row_to_agent(r) for r in c.execute(
                select(agents_table).where(agents_table.c.engagement_id == engagement_id)
            ).all()]

    # ── Prospects ─────────────────────────────────────────────────────────

    def save_prospect(self, prospect: Prospect, *, tenant_id: Optional[str] = None) -> None:
        values = {
            "id": prospect.id,
            "tenant_id": tenant_id,
            "engagement_id": prospect.engagement_id,
            "email": prospect.email,
            "full_name": prospect.full_name,
            "company": prospect.company,
            "title": prospect.title,
            "raw": dict(prospect.raw),
            "research": dict(prospect.research),
            "status": prospect.status,
            "created_at": prospect.created_at,
        }
        with self._holder.conn() as c:
            existing = c.execute(select(prospects_table.c.id).where(prospects_table.c.id == prospect.id)).first()
            if existing:
                c.execute(prospects_table.update().where(prospects_table.c.id == prospect.id).values(**values))
            else:
                c.execute(prospects_table.insert().values(**values))

    def get_prospect(self, prospect_id: str) -> Optional[Prospect]:
        with self._holder.conn() as c:
            row = c.execute(select(prospects_table).where(prospects_table.c.id == prospect_id)).first()
            return _row_to_prospect(row) if row else None

    def list_prospects(
        self,
        engagement_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 100,
        tenant_id: Optional[str] = None,
        cursor: Optional[str] = None,  # M10: keyset pagination
    ) -> Iterable[Prospect]:
        stmt = select(prospects_table).where(prospects_table.c.engagement_id == engagement_id)
        if tenant_id is not None:
            stmt = stmt.where(prospects_table.c.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(prospects_table.c.status == status)
        if cursor is not None:
            stmt = stmt.where(prospects_table.c.id > cursor)
        stmt = stmt.order_by(prospects_table.c.id).limit(limit)
        with self._holder.conn() as c:
            return [_row_to_prospect(r) for r in c.execute(stmt).all()]

    def list_prospects_cursor(
        self,
        engagement_id: str,
        *,
        cursor: Optional[str] = None,
        limit: int = 50,
        tenant_id: Optional[str] = None,
    ) -> "tuple[list[Prospect], Optional[str]]":
        """M10: keyset cursor pagination. Returns (items, next_cursor)."""
        stmt = select(prospects_table).where(prospects_table.c.engagement_id == engagement_id)
        if tenant_id is not None:
            stmt = stmt.where(prospects_table.c.tenant_id == tenant_id)
        if cursor:
            stmt = stmt.where(prospects_table.c.id > cursor)
        stmt = stmt.order_by(prospects_table.c.id.asc()).limit(limit + 1)
        with self._holder.conn() as c:
            rows = c.execute(stmt).all()
        has_more = len(rows) > limit
        items = [_row_to_prospect(r) for r in rows[:limit]]
        next_cursor = items[-1].id if has_more and items else None
        return items, next_cursor

    # ── Jobs ──────────────────────────────────────────────────────────────

    def save_job(self, job: Job) -> None:
        job.updated_at = datetime.now(timezone.utc)
        values = {
            "id": job.id, "engagement_id": job.engagement_id,
            "agent_id": job.agent_id, "kind": job.kind.value,
            "payload": dict(job.payload), "state": job.state,
            "prospect_id": job.prospect_id, "parent_job_id": job.parent_job_id,
            "requires_approval": job.requires_approval,
            "scheduled_for": job.scheduled_for, "not_before": job.not_before,
            "attempt": job.attempt, "max_attempts": job.max_attempts,
            "last_error": job.last_error, "result": dict(job.result),
            "created_at": job.created_at, "updated_at": job.updated_at,
        }
        with self._holder.conn() as c:
            existing = c.execute(select(jobs_table.c.id).where(jobs_table.c.id == job.id)).first()
            if existing:
                c.execute(jobs_table.update().where(jobs_table.c.id == job.id).values(**values))
            else:
                c.execute(jobs_table.insert().values(**values))

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._holder.conn() as c:
            row = c.execute(select(jobs_table).where(jobs_table.c.id == job_id)).first()
            return _row_to_job(row) if row else None

    def list_due_jobs(self, *, limit: int = 100) -> Iterable[Job]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(jobs_table)
            .where(jobs_table.c.state.in_(("pending", "approved")))
            .where(jobs_table.c.scheduled_for <= now)
            .where((jobs_table.c.not_before.is_(None)) | (jobs_table.c.not_before <= now))
            .order_by(jobs_table.c.scheduled_for).limit(limit)
        )
        with self._holder.conn() as c:
            return [_row_to_job(r) for r in c.execute(stmt).all()]

    def list_jobs_by_state(
        self,
        state: str,
        *,
        engagement_id: Optional[str] = None,
        limit: int = 100,
    ) -> Iterable[Job]:
        stmt = select(jobs_table).where(jobs_table.c.state == state)
        if engagement_id is not None:
            stmt = stmt.where(jobs_table.c.engagement_id == engagement_id)
        stmt = stmt.order_by(jobs_table.c.scheduled_for).limit(limit)
        with self._holder.conn() as c:
            return [_row_to_job(r) for r in c.execute(stmt).all()]

    # ── Replies ───────────────────────────────────────────────────────────

    def save_reply(self, reply: Reply) -> None:
        values = {
            "id": reply.id, "engagement_id": reply.engagement_id,
            "prospect_id": reply.prospect_id, "job_id": reply.job_id,
            "snippet": reply.snippet, "classification": reply.classification,
            "suggested_reply": reply.suggested_reply, "status": reply.status,
            "received_at": reply.received_at, "external_message_id": reply.external_message_id,
        }
        with self._holder.conn() as c:
            existing = c.execute(select(replies_table.c.id).where(replies_table.c.id == reply.id)).first()
            if existing:
                c.execute(replies_table.update().where(replies_table.c.id == reply.id).values(**values))
            else:
                c.execute(replies_table.insert().values(**values))

    def get_reply(self, reply_id: str) -> Optional[Reply]:
        with self._holder.conn() as c:
            row = c.execute(select(replies_table).where(replies_table.c.id == reply_id)).first()
            return _row_to_reply(row) if row else None

    def list_replies(
        self, engagement_id: str, *, status: Optional[str] = None, limit: int = 100,
    ) -> Iterable[Reply]:
        stmt = select(replies_table).where(replies_table.c.engagement_id == engagement_id)
        if status is not None:
            stmt = stmt.where(replies_table.c.status == status)
        stmt = stmt.order_by(replies_table.c.received_at.desc()).limit(limit)
        with self._holder.conn() as c:
            return [_row_to_reply(r) for r in c.execute(stmt).all()]

    def get_reply_by_external_id(self, external_message_id: str) -> Optional[Reply]:
        with self._holder.conn() as c:
            row = c.execute(
                select(replies_table).where(replies_table.c.external_message_id == external_message_id)
            ).first()
            return _row_to_reply(row) if row else None

    # ── Meetings ──────────────────────────────────────────────────────────

    def save_meeting(self, meeting: Meeting) -> None:
        values = {
            "id": meeting.id, "engagement_id": meeting.engagement_id,
            "prospect_id": meeting.prospect_id, "reply_id": meeting.reply_id,
            "scheduled_for": meeting.scheduled_for, "status": meeting.status,
            "booked_at": meeting.booked_at, "notes": meeting.notes,
        }
        with self._holder.conn() as c:
            existing = c.execute(select(meetings_table.c.id).where(meetings_table.c.id == meeting.id)).first()
            if existing:
                c.execute(meetings_table.update().where(meetings_table.c.id == meeting.id).values(**values))
            else:
                c.execute(meetings_table.insert().values(**values))

    def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        with self._holder.conn() as c:
            row = c.execute(select(meetings_table).where(meetings_table.c.id == meeting_id)).first()
            return _row_to_meeting(row) if row else None

    def list_meetings(
        self, engagement_id: str, *, status: Optional[str] = None, limit: int = 100,
    ) -> Iterable[Meeting]:
        stmt = select(meetings_table).where(meetings_table.c.engagement_id == engagement_id)
        if status is not None:
            stmt = stmt.where(meetings_table.c.status == status)
        stmt = stmt.order_by(meetings_table.c.scheduled_for.desc()).limit(limit)
        with self._holder.conn() as c:
            return [_row_to_meeting(r) for r in c.execute(stmt).all()]


# ─────────────────────────────────────────────────────────────────────────────
# EventSink
# ─────────────────────────────────────────────────────────────────────────────


class SqliteEventSink:
    """Append-only event log."""

    def __init__(self, holder: _EngineHolder) -> None:
        self._holder = holder

    def emit(self, event: Event) -> None:
        with self._holder.conn() as c:
            c.execute(
                events_table.insert().values(
                    id=event.id,
                    kind=event.kind.value,
                    engagement_id=event.engagement_id,
                    agent_id=event.agent_id,
                    job_id=event.job_id,
                    prospect_id=event.prospect_id,
                    payload=dict(event.payload),
                    occurred_at=event.occurred_at,
                )
            )

    def list_recent(
        self,
        *,
        engagement_id: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 100,
    ) -> Iterable[Event]:
        stmt = select(events_table)
        if engagement_id is not None:
            stmt = stmt.where(events_table.c.engagement_id == engagement_id)
        if kind is not None:
            stmt = stmt.where(events_table.c.kind == kind)
        stmt = stmt.order_by(events_table.c.occurred_at.desc()).limit(limit)
        with self._holder.conn() as c:
            return [_row_to_event(r) for r in c.execute(stmt).all()]


# ─────────────────────────────────────────────────────────────────────────────
# CostLedger
# ─────────────────────────────────────────────────────────────────────────────


class SqliteCostLedger:
    """Per-engagement cost tracking + budget enforcement."""

    def __init__(self, holder: _EngineHolder) -> None:
        self._holder = holder

    def debit(self, entry: CostEntry) -> None:
        with self._holder.conn() as c:
            c.execute(
                cost_entries_table.insert().values(
                    id=entry.id,
                    engagement_id=entry.engagement_id,
                    job_id=entry.job_id,
                    category=entry.category,
                    amount_cents=entry.amount_cents,
                    metadata_json=dict(entry.metadata),
                    occurred_at=entry.occurred_at,
                )
            )

    def total_spent_cents(
        self,
        engagement_id: str,
        *,
        category: Optional[str] = None,
    ) -> int:
        from sqlalchemy import func

        stmt = select(func.coalesce(func.sum(cost_entries_table.c.amount_cents), 0)).where(
            cost_entries_table.c.engagement_id == engagement_id
        )
        if category is not None:
            stmt = stmt.where(cost_entries_table.c.category == category)
        with self._holder.conn() as c:
            return int(c.execute(stmt).scalar_one())

    def remaining_budget_cents(self, engagement_id: str) -> Optional[int]:
        with self._holder.conn() as c:
            row = c.execute(
                select(engagements_table.c.monthly_budget_cents).where(
                    engagements_table.c.id == engagement_id
                )
            ).first()
            if row is None or row.monthly_budget_cents is None:
                return None
            spent = self.total_spent_cents(engagement_id)
            return max(0, row.monthly_budget_cents - spent)

    def list_recent(
        self,
        engagement_id: str,
        *,
        limit: int = 100,
    ) -> Iterable[CostEntry]:
        stmt = (
            select(cost_entries_table)
            .where(cost_entries_table.c.engagement_id == engagement_id)
            .order_by(cost_entries_table.c.occurred_at.desc())
            .limit(limit)
        )
        with self._holder.conn() as c:
            return [_row_to_cost(r) for r in c.execute(stmt).all()]
