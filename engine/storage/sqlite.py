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
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.engine import Connection

from engine.auth.models import Tenant, User
from engine.core.types import (
    Account,
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
from engine.security.secrets import decrypt_json_blob, decrypt_text, encrypt_json_blob, encrypt_text

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
    Column("trial_ends_at", DateTime(timezone=True), nullable=True),
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


accounts_table = Table(
    "accounts",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("engagement_id", String, nullable=False, index=True),
    Column("company_domain", String, nullable=False, index=True),
    Column("company_name", String, nullable=True),
    Column("evidence_json", JSON, nullable=False, default=list),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "engagement_id", "company_domain", name="uq_account_tenant_eng_domain"),
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


# ── Signal Intelligence (Attainly Signal Platform) ─────────────────────────────

signal_sources_table = Table(
    "signal_sources",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("connector_kind", String, nullable=False),
    Column("name", String, nullable=False),
    Column("config_json", JSON, nullable=False, default=dict),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

signal_events_table = Table(
    "signal_events",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("source_id", String, nullable=False, index=True),
    Column("source_event_id", String, nullable=False),
    Column("signal_type", String, nullable=False, index=True),
    Column("entity_type", String, nullable=False, default="company"),
    Column("entity_id", String, nullable=True),
    Column("company_domain", String, nullable=False, index=True),
    Column("company_name", String, nullable=True),
    Column("person_identifier", String, nullable=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False, index=True),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("confidence", String, nullable=False, default="0.85"),
    Column("evidence_json", JSON, nullable=False, default=dict),
    Column("source_url", String, nullable=True),
    Column("raw_payload_json", JSON, nullable=False, default=dict),
    Column("metadata_json", JSON, nullable=False, default=dict),
    Column("trace_id", String, nullable=True, index=True),
    Column("schema_version", String, nullable=False, default="1.0.0"),
    Column("freshness", String, nullable=False, default="manual"),
    Column("canonical_signal_id", String, nullable=True, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

canonical_signals_table = Table(
    "canonical_signals",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("signal_type", String, nullable=False, index=True),
    Column("company_domain", String, nullable=False, index=True),
    Column("entity_type", String, nullable=False, default="company"),
    Column("entity_id", String, nullable=True),
    Column("company_name", String, nullable=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("confidence", String, nullable=False, default="0.85"),
    Column("evidence_json", JSON, nullable=False, default=dict),
    Column("source_count", Integer, nullable=False, default=1),
    Column("source_event_ids_json", JSON, nullable=False, default=list),
    Column("first_observed_at", DateTime(timezone=True), nullable=False),
    Column("last_observed_at", DateTime(timezone=True), nullable=False, index=True),
    Column("metadata_json", JSON, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

signal_connector_state_table = Table(
    "signal_connector_state",
    metadata,
    Column("source_id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("last_cursor", String, nullable=True),
    Column("last_success_at", DateTime(timezone=True), nullable=True),
    Column("last_event_at", DateTime(timezone=True), nullable=True),
    Column("error_state", Text, nullable=True),
    Column("retry_count", Integer, nullable=False, default=0),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

signal_ingestion_runs_table = Table(
    "signal_ingestion_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("source_id", String, nullable=False, index=True),
    Column("connector_kind", String, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=False),
    Column("events_seen", Integer, nullable=False, default=0),
    Column("events_created", Integer, nullable=False, default=0),
    Column("events_deduped", Integer, nullable=False, default=0),
    Column("signals_rejected", Integer, nullable=False, default=0),
    Column("prospects_created", Integer, nullable=False, default=0),
    Column("duration_ms", Integer, nullable=False, default=0),
    Column("error_state", Text, nullable=True),
    Column("trace_id", String, nullable=True, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

mcp_audit_events_table = Table(
    "mcp_audit_events",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("actor", String, nullable=False),
    Column("tool_name", String, nullable=False, index=True),
    Column("arguments_hash", String, nullable=False),
    Column("arguments_safe", Text, nullable=False),
    Column("result_status", String, nullable=False),
    Column("trace_id", String, nullable=True),
    Column("error", Text, nullable=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False, index=True),
)

signal_webhook_replays_table = Table(
    "signal_webhook_replays",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("source_id", String, nullable=False, index=True),
    Column("replay_key", String, nullable=False),
    Column("nonce", String, nullable=True),
    Column("body_hash", String, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
    UniqueConstraint("tenant_id", "source_id", "replay_key", name="uq_webhook_replay_key"),
    UniqueConstraint("tenant_id", "source_id", "nonce", name="uq_webhook_nonce"),
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


def _row_to_account(row: Any):
    from engine.core.types import Account

    return Account(
        id=row.id,
        tenant_id=row.tenant_id,
        engagement_id=row.engagement_id,
        company_domain=row.company_domain,
        company_name=row.company_name,
        evidence=list(_coerce_json(row.evidence_json) or []),
        created_at=_ensure_utc(row.created_at),
        updated_at=_ensure_utc(row.updated_at),
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
        trial_ends_at=_ensure_utc(row.trial_ends_at) if getattr(row, "trial_ends_at", None) else None,
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
        credentials_json=decrypt_json_blob(_coerce_json(row.credentials_json)) if row.credentials_json else None,
        oauth_client_id=row.oauth_client_id,
        oauth_client_secret=decrypt_text(row.oauth_client_secret),
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


def _migrate_add_columns(engine: Engine) -> None:
    """
    Tiny additive-migration helper: add columns introduced after initial
    release to existing databases. SQLAlchemy's create_all never alters
    existing tables, so we ADD COLUMN by hand (idempotent, IF NOT EXISTS where
    supported). Only nullable columns with no default are added this way.
    """
    from sqlalchemy import inspect as _inspect

    inspector = _inspect(engine)
    try:
        existing_cols = {c["name"] for c in inspector.get_columns("tenants")}
    except Exception:
        return  # table not present yet (fresh create_all handles it)

    if "trial_ends_at" not in existing_cols:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE tenants ADD COLUMN trial_ends_at TIMESTAMP"
            )

    # Signal intelligence additive migrations
    try:
        connector_cols = {c["name"] for c in inspector.get_columns("signal_connector_state")}
        if "tenant_id" not in connector_cols:
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "ALTER TABLE signal_connector_state ADD COLUMN tenant_id VARCHAR"
                )
    except Exception:
        pass


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

    # Azure/prod secrets may use postgresql+psycopg:// (v3). Prefer the
    # driver that is actually installed so a missing optional package does
    # not crash-loop the web tier.
    if url.startswith("postgresql+") or url.startswith("postgresql://"):
        try:
            import psycopg  # noqa: F401
            if url.startswith("postgresql://"):
                url = "postgresql+psycopg://" + url[len("postgresql://") :]
        except ImportError:
            if "+psycopg://" in url and "+psycopg2://" not in url:
                url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)

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
    _migrate_add_columns(engine)
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
            "trial_ends_at": tenant.trial_ends_at,
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
            "credentials_json": encrypt_json_blob(dict(mailbox.credentials_json)) if mailbox.credentials_json else None,
            "oauth_client_id": mailbox.oauth_client_id,
            "oauth_client_secret": encrypt_text(mailbox.oauth_client_secret),
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

    def list_all_mailboxes(self, *, status: Optional[str] = None):
        stmt = select(mailboxes_table)
        if status is not None:
            stmt = stmt.where(mailboxes_table.c.status == status)
        with self._holder.conn() as c:
            return [_row_to_mailbox(r) for r in c.execute(stmt).all()]

    def update_mailbox_credentials(self, mailbox_id: str, *, credentials_json: dict) -> None:
        with self._holder.conn() as c:
            c.execute(mailboxes_table.update().where(mailboxes_table.c.id == mailbox_id).values(
                credentials_json=encrypt_json_blob(dict(credentials_json)),
                updated_at=datetime.now(timezone.utc),
            ))

    def update_mailbox_status(self, mailbox_id: str, *, status: str, last_error: Optional[str] = None) -> None:
        vals = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if last_error is not None:
            vals["last_error"] = last_error
        with self._holder.conn() as c:
            c.execute(mailboxes_table.update().where(mailboxes_table.c.id == mailbox_id).values(**vals))

    def bump_mailbox_send_count(self, mailbox_id: str, *, amount: int = 1) -> None:
        """Atomically increment today's send counter — feeds the daily-cap gate.

        SQL-level increment (not read-modify-write) so concurrent workers can't
        clobber each other's counts and over-send past the mailbox's daily cap.
        """
        with self._holder.conn() as c:
            c.execute(
                mailboxes_table.update()
                .where(mailboxes_table.c.id == mailbox_id)
                .values(
                    emails_sent_today=mailboxes_table.c.emails_sent_today + amount,
                    updated_at=datetime.now(timezone.utc),
                )
            )

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

    def ignore_orphaned_reply(self, orphan_id: str, *, tenant_id: Optional[str] = None) -> bool:
        with self._holder.conn() as c:
            stmt = select(orphaned_replies_table.c.id).where(orphaned_replies_table.c.id == orphan_id)
            if tenant_id is not None:
                stmt = stmt.where(orphaned_replies_table.c.tenant_id == tenant_id)
            existing = c.execute(stmt).first()
            if not existing:
                return False
            c.execute(orphaned_replies_table.update().where(
                orphaned_replies_table.c.id == orphan_id).values(status="ignored"))
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

    def get_engagement_tenant_id(self, engagement_id: str) -> Optional[str]:
        """Return the tenant that owns an engagement without hydrating the public dataclass."""
        with self._holder.conn() as c:
            row = c.execute(
                select(engagements_table.c.tenant_id).where(engagements_table.c.id == engagement_id)
            ).first()
            return row.tenant_id if row else None

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
        if tenant_id is None:
            with self._holder.conn() as c:
                row = c.execute(
                    select(engagements_table.c.tenant_id).where(
                        engagements_table.c.id == agent.engagement_id
                    )
                ).first()
                tenant_id = row.tenant_id if row else None
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
        if tenant_id is None:
            with self._holder.conn() as c:
                row = c.execute(
                    select(engagements_table.c.tenant_id).where(
                        engagements_table.c.id == prospect.engagement_id
                    )
                ).first()
                tenant_id = row.tenant_id if row else None
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

    def count_prospects_for_tenant(self, tenant_id: str) -> int:
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(prospects_table)
            .where(prospects_table.c.tenant_id == tenant_id)
        )
        with self._holder.conn() as c:
            return int(c.execute(stmt).scalar() or 0)

    # ── Accounts ──────────────────────────────────────────────────────────

    def save_account(self, account) -> None:
        from engine.core.types import Account as _Account

        values = {
            "id": account.id,
            "tenant_id": account.tenant_id,
            "engagement_id": account.engagement_id,
            "company_domain": account.company_domain,
            "company_name": account.company_name,
            "evidence_json": list(account.evidence or []),
            "created_at": account.created_at,
            "updated_at": account.updated_at,
        }
        with self._holder.conn() as c:
            existing = c.execute(select(accounts_table.c.id).where(accounts_table.c.id == account.id)).first()
            if existing:
                c.execute(accounts_table.update().where(accounts_table.c.id == account.id).values(**values))
            else:
                c.execute(accounts_table.insert().values(**values))

    def get_account(self, account_id: str):
        with self._holder.conn() as c:
            row = c.execute(select(accounts_table).where(accounts_table.c.id == account_id)).first()
            return _row_to_account(row) if row else None

    def list_accounts(self, engagement_id: str, *, tenant_id: str):
        stmt = (
            select(accounts_table)
            .where(accounts_table.c.engagement_id == engagement_id)
            .where(accounts_table.c.tenant_id == tenant_id)
            .order_by(accounts_table.c.company_domain)
        )
        with self._holder.conn() as c:
            return [_row_to_account(r) for r in c.execute(stmt).all()]

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
        tenant_id = None
        with self._holder.conn() as c:
            row = c.execute(
                select(engagements_table.c.tenant_id).where(
                    engagements_table.c.id == job.engagement_id
                )
            ).first()
            tenant_id = row.tenant_id if row else None
        values = {
            "id": job.id, "tenant_id": tenant_id, "engagement_id": job.engagement_id,
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

    def list_due_jobs(
        self,
        *,
        limit: int = 100,
        engagement_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Iterable[Job]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(jobs_table)
            .where(jobs_table.c.state.in_(("pending", "approved")))
            .where(jobs_table.c.scheduled_for <= now)
            .where((jobs_table.c.not_before.is_(None)) | (jobs_table.c.not_before <= now))
        )
        if engagement_id is not None:
            stmt = stmt.where(jobs_table.c.engagement_id == engagement_id)
        if tenant_id is not None:
            stmt = stmt.join(
                engagements_table,
                jobs_table.c.engagement_id == engagements_table.c.id,
            ).where(engagements_table.c.tenant_id == tenant_id)
        stmt = stmt.order_by(jobs_table.c.scheduled_for).limit(limit)
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

    def upsert_prospect(self, prospect: Prospect, *, tenant_id: Optional[str] = None) -> None:
        self.save_prospect(prospect, tenant_id=tenant_id)

    def _ensure_kv_table(self) -> None:
        from sqlalchemy import text as sa_text
        with self._holder.engine.begin() as c:
            c.execute(
                sa_text(
                    "CREATE TABLE IF NOT EXISTS autoreach_kv_store ("
                    "key VARCHAR(255) PRIMARY KEY, "
                    "value_text TEXT NOT NULL, "
                    "updated_at VARCHAR(64) NOT NULL"
                    ")"
                )
            )

    def get_kv(self, key: str) -> Optional[str]:
        from sqlalchemy import text as sa_text
        self._ensure_kv_table()
        with self._holder.engine.begin() as c:
            row = c.execute(
                sa_text("SELECT value_text FROM autoreach_kv_store WHERE key = :k"),
                {"k": key},
            ).first()
            return str(row[0]) if row else None

    def set_kv(self, key: str, value: str) -> None:
        from sqlalchemy import text as sa_text
        self._ensure_kv_table()
        now = datetime.now(timezone.utc).isoformat()
        with self._holder.engine.begin() as c:
            existing = c.execute(
                sa_text("SELECT key FROM autoreach_kv_store WHERE key = :k"),
                {"k": key},
            ).first()
            if existing:
                c.execute(
                    sa_text("UPDATE autoreach_kv_store SET value_text = :v, updated_at = :u WHERE key = :k"),
                    {"k": key, "v": str(value), "u": now},
                )
            else:
                c.execute(
                    sa_text("INSERT INTO autoreach_kv_store (key, value_text, updated_at) VALUES (:k, :v, :u)"),
                    {"k": key, "v": str(value), "u": now},
                )



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
