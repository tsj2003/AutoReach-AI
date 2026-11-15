"""
Celery application for distributed engine execution (production scale).

Architecture
------------
In dev (no REDIS_URL), the cockpit runs ticks inline — simple, synchronous,
perfect for a single operator. In production (REDIS_URL set), the cockpit
dispatches tick/poll work to Celery so:
    * the web process stays responsive (no long-running sends in the request)
    * work survives web restarts (Redis-backed queue)
    * we scale horizontally (add worker dynos)

Tasks are thin: they rebuild the engine runtime from env config and call the
same EngineRuntime methods the inline path uses. No logic duplication.

Beat schedule:
    * engine.tick_all_active     every 60s — plan + execute due jobs
    * engine.reset_daily_caps    daily   — reset mailbox send counters
    * engine.warmup_tick_all     daily   — advance mailbox warmup ramps
"""

from __future__ import annotations

import logging
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from celery import Celery

logger = logging.getLogger(__name__)


def _normalize_redis_url(url: str) -> str:
    """Make managed TLS Redis/Valkey URLs acceptable to Celery/Kombu."""
    if not url.startswith("rediss://"):
        return url

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("ssl_cert_reqs", "CERT_REQUIRED")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


REDIS_URL = _normalize_redis_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

celery_app = Celery(
    "autoreach_engine",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86_400,
    task_routes={
        "engine.tick_engagement": {"queue": "engine"},
        "engine.poll_replies": {"queue": "engine"},
        "engine.intent_ingest_campaign": {"queue": "engine"},
        "engine.discover_campaign_people": {"queue": "engine"},
        "engine.tasks.dispatch_agent_task": {"queue": "standard-agents"},
        "engine.tick_all_active": {"queue": "engine"},
        "engine.reset_daily_caps": {"queue": "maintenance"},
        "engine.warmup_tick_all": {"queue": "maintenance"},
        "engine.ingest_active_signal_connectors": {"queue": "engine"},
    },
    beat_schedule={
        "tick-all-active": {
            "task": "engine.tick_all_active",
            "schedule": 60.0,
        },
        "reset-daily-caps": {
            "task": "engine.reset_daily_caps",
            "schedule": 86_400.0,
        },
        "warmup-tick-all": {
            "task": "engine.warmup_tick_all",
            "schedule": 86_400.0,
        },
        "ingest-signal-connectors": {
            "task": "engine.ingest_active_signal_connectors",
            "schedule": 900.0,
        },
    },
)


def _build_runtime():
    """Rebuild the engine runtime + services from env config inside a task."""
    from engine.telemetry.provider import setup_phoenix_telemetry_from_env
    from engine import (
        AdapterRegistry, ConsoleEmailAdapter, EngineRuntime,
        JsonFileTokenStore, OutboundAgentV1, RealGmailSendAdapter, open_storage,
    )

    setup_phoenix_telemetry_from_env()

    db_url = os.getenv("DATABASE_URL") or os.getenv("AUTOREACH_DB", "sqlite:///autoreach_engine.db")
    store, events, ledger = open_storage(db_url)

    # Choose adapter the same way the cockpit does.
    from engine.dispatch.linkedin_adapter import LinkedInVoyagerAdapter

    linkedin_adapter = LinkedInVoyagerAdapter(store=store, events=events, ledger=ledger)
    if os.getenv("AUTOREACH_RUNTIME_SMART_DISPATCH", "").strip().lower() in ("1", "true", "yes", "on"):
        from engine.dispatch import SmartRoutedEmailAdapter

        email_adapter = SmartRoutedEmailAdapter(store=store, events=events, ledger=ledger)
    else:
        token_path = os.getenv("AUTOREACH_GMAIL_TOKEN_PATH")
        sender = os.getenv("AUTOREACH_GMAIL_SENDER", "")
        if token_path and sender:
            email_adapter = RealGmailSendAdapter(
                sender_email=sender,
                token_store=JsonFileTokenStore(token_path=token_path),
                dry_run=os.getenv("AUTOREACH_GMAIL_DRY_RUN", "").lower() in ("1", "true", "yes"),
            )
        else:
            email_adapter = ConsoleEmailAdapter()

    runtime = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([linkedin_adapter, email_adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
        # Multi-tenant worker: unscoped sweeps must be explicit (allow_all_tenants).
        require_tenant_scope=True,
    )
    return runtime, store, events, ledger


@celery_app.task(name="engine.tick_engagement", bind=True, max_retries=3, default_retry_delay=60)
def tick_engagement(self, engagement_id: str):
    """Run one plan+execute tick for a single engagement."""
    runtime, *_ = _build_runtime()
    try:
        return runtime.tick(engagement_id=engagement_id)
    except Exception as exc:
        logger.exception("tick_engagement failed for %s", engagement_id)
        raise self.retry(exc=exc)


@celery_app.task(name="engine.poll_replies", bind=True)
def poll_replies(self, engagement_id: str):
    """Run a Gmail reply-detection pass for an engagement."""
    from engine.llm import GeminiClient
    from engine.adapters.gmail_token_store import JsonFileTokenStore
    from engine.services import GmailReplyDetector, TenantMailboxReplyDetector

    runtime, store, events, ledger = _build_runtime()
    from engine.services import OperationsService
    ops = OperationsService(store=store, events=events)

    if os.getenv("AUTOREACH_RUNTIME_SMART_DISPATCH", "").strip().lower() in ("1", "true", "yes", "on"):
        detector = TenantMailboxReplyDetector(
            store=store,
            events=events,
            ledger=ledger,
            ops=ops,
            gemini=GeminiClient(),
        )
        result = detector.poll(engagement_id)
        return {"replies_recorded": result.replies_recorded, "scanned": result.prospects_scanned}

    token_path = os.getenv("AUTOREACH_GMAIL_TOKEN_PATH")
    sender = os.getenv("AUTOREACH_GMAIL_SENDER", "")
    if not (token_path and sender):
        return {"skipped": "gmail not configured"}

    detector = GmailReplyDetector(
        store=store, events=events, ledger=ledger, ops=ops,
        token_store=JsonFileTokenStore(token_path=token_path),
        sender_email=sender, gemini=GeminiClient(),
    )
    result = detector.poll(engagement_id)
    return {"replies_recorded": result.replies_recorded, "scanned": result.prospects_scanned}


@celery_app.task(name="engine.discover_campaign_people", bind=True, max_retries=2, default_retry_delay=30)
def discover_campaign_people(
    self,
    campaign_id: str,
    tenant_id: str,
    cap: int = 20,
):
    """Fill a campaign with ICP people-search prospects (LinkedIn dorks + optional team pages)."""
    from engine.services.people_discovery import run_campaign_people_discovery

    _, store, *_ = _build_runtime()
    try:
        return run_campaign_people_discovery(
            store,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            cap=cap,
        )
    except Exception as exc:
        logger.exception("discover_campaign_people failed campaign=%s", campaign_id)
        raise self.retry(exc=exc)


@celery_app.task(name="engine.intent_ingest_campaign", bind=True, max_retries=3, default_retry_delay=60)
def intent_ingest_campaign(
    self,
    *,
    tenant_id: str,
    engagement_id: str,
    duckdb_path: str | None = None,
    hours_back: int | None = None,
):
    """Ingest recent tenant intent signals into campaign prospects."""
    from engine.intent.ingestor import IntentProspectIngestor
    from engine.intent.repository import DuckDBIntentRepository

    _, store, events, _ = _build_runtime()
    resolved_duckdb_path = duckdb_path or os.getenv("AUTOREACH_INTENT_DUCKDB_PATH")
    if not resolved_duckdb_path:
        raise ValueError("AUTOREACH_INTENT_DUCKDB_PATH is required")
    resolved_hours_back = int(hours_back or os.getenv("AUTOREACH_INTENT_HOURS_BACK", "24"))
    repository = DuckDBIntentRepository(db_path=resolved_duckdb_path)
    ingestor = IntentProspectIngestor(store=store, events=events, repository=repository)
    try:
        result = ingestor.ingest_campaign(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            hours_back=resolved_hours_back,
        )
        return result.model_dump()
    except Exception as exc:
        logger.exception("intent_ingest_campaign failed tenant=%s engagement=%s", tenant_id, engagement_id)
        raise self.retry(exc=exc)


@celery_app.task(name="engine.tick_all_active")
def tick_all_active():
    """Beat task: tick all active engagements (drains due jobs across tenants)."""
    from engine.signals.feature_flags import is_engine_paused

    if is_engine_paused():
        logger.warning("engine.tick_all_active skipped — AUTOREACH_ENGINE_PAUSED=1")
        return {"planned": 0, "executed": 0, "iterations": 0, "paused": True}
    runtime, store, *_ = _build_runtime()
    # The one legitimate system-wide sweep — declared explicitly.
    result = runtime.run_once(max_iters=10, allow_all_tenants=True)
    return result


@celery_app.task(name="engine.reset_daily_caps")
def reset_daily_caps():
    """Beat task: reset per-mailbox daily send counters across all tenants."""
    from engine.auth.mailbox_models import Mailbox
    from datetime import datetime, timezone

    _, store, _, _ = _build_runtime()
    count = 0
    for mb in store.list_all_mailboxes():
        if mb.emails_sent_today != 0:
            store.save_mailbox(Mailbox(
                id=mb.id, tenant_id=mb.tenant_id, user_id=mb.user_id,
                provider=mb.provider, email_address=mb.email_address,
                display_name=mb.display_name, credentials_json=mb.credentials_json,
                oauth_client_id=mb.oauth_client_id, oauth_client_secret=mb.oauth_client_secret,
                max_emails_per_day=mb.max_emails_per_day, emails_sent_today=0,
                last_send_reset=datetime.now(timezone.utc), warmup_day=mb.warmup_day,
                status=mb.status, reputation_score=mb.reputation_score,
                last_error=mb.last_error, created_at=mb.created_at,
                updated_at=datetime.now(timezone.utc),
            ))
            count += 1
    return {"reset": count}


@celery_app.task(name="engine.warmup_tick_all")
def warmup_tick_all():
    """Beat task: advance mailbox warmup ramps across all tenants."""
    from engine.services.mailbox_health import MailboxHealthMonitor

    _, store, events, _ = _build_runtime()
    mon = MailboxHealthMonitor(store=store, events=events)
    total = 0
    for tid in {mb.tenant_id for mb in store.list_all_mailboxes() if mb.tenant_id}:
        total += mon.warmup_tick(tid)
    return {"advanced": total}


@celery_app.task(name="engine.ingest_active_signal_connectors")
def ingest_active_signal_connectors():
    """Beat task: sync enabled signal connectors per tenant (failures isolated)."""
    from engine.signals.feature_flags import is_signals_enabled
    from engine.signals.repository import SignalRepository
    from engine.signals.service import SignalConnectorService

    if not is_signals_enabled():
        return {"skipped": "AUTOREACH_SIGNALS_ENABLED=0"}

    _, store, events, _ = _build_runtime()
    repo = SignalRepository(store._holder.engine)
    service = SignalConnectorService(repository=repo, store=store, events=events)

    summary = []
    for tenant_id in repo.list_tenant_ids_with_enabled_sources():
        try:
            results = service.sync_all_enabled(tenant_id=tenant_id)
            summary.append({
                "tenant_id": tenant_id,
                "sources_synced": len(results),
                "events_inserted": sum(r.ingestion.events_inserted for r in results),
                "prospects_created": sum(r.prospects_created for r in results),
                "errors": [r.error for r in results if r.error],
            })
        except Exception as exc:
            logger.exception("signal connector ingest failed tenant=%s", tenant_id)
            summary.append({"tenant_id": tenant_id, "error": str(exc)})
    return {"tenants_processed": len(summary), "results": summary}
