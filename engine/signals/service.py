"""Connector factory and orchestrated sync with campaign ingestion."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from engine.intent.ingestor import IntentProspectIngestor
from engine.signals.bridge import StoreIntentRepository
from engine.signals.connectors.base import SignalConnector
from engine.signals.connectors.manual import ManualSignalConnector
from engine.signals.connectors.rss import RSSSignalConnector
from engine.signals.ingestion import IngestionResult, SignalIngestionService
from engine.signals.repository import SignalRepository
from engine.signals.observability import SignalIngestionRun

logger = logging.getLogger(__name__)


@dataclass
class ConnectorSyncResult:
    source_id: str
    tenant_id: str
    ingestion: IngestionResult
    prospects_created: int = 0
    prospects_skipped: int = 0
    campaign_ids: list[str] = field(default_factory=list)
    error: str | None = None


def build_connector(source: dict[str, Any]) -> SignalConnector:
    """Instantiate connector from persisted source config."""

    kind = source.get("connector_kind", "")
    config = source.get("config") or {}
    source_id = source["id"]
    if kind == "rss":
        return RSSSignalConnector(
            source_id=source_id,
            feed_url=config.get("feed_url"),
            allowed_signal_types=config.get("allowed_signal_types"),
            max_entries=int(config.get("max_entries", 50)),
        )
    if kind == "manual":
        return ManualSignalConnector(source_id=source_id)
    if kind == "webhook":
        from engine.signals.connectors.webhook import WebhookSignalConnector
        return WebhookSignalConnector(
            source_id=source_id,
            webhook_secret=config.get("webhook_secret"),
        )
    from engine.signals.connectors.base import NotConfiguredConnector
    return NotConfiguredConnector(
        connector_kind=kind or "unknown",
        label=kind or "unknown",
        message=f"NOT CONFIGURED — unsupported connector kind: {kind}",
    )


class SignalConnectorService:
    """Tenant-scoped connector management and sync."""

    def __init__(
        self,
        *,
        repository: SignalRepository,
        store,
        events,
    ) -> None:
        self._repo = repository
        self._ingestion = SignalIngestionService(repository=repository)
        self._store = store
        self._events = events

    def sync_source(
        self,
        *,
        tenant_id: str,
        source_id: str,
        ingest_campaigns: bool = True,
        hours_back: int = 168,
    ) -> ConnectorSyncResult:
        started = datetime.now(timezone.utc)
        source = self._repo.get_source(source_id, tenant_id=tenant_id)
        if source is None:
            return ConnectorSyncResult(
                source_id=source_id,
                tenant_id=tenant_id,
                ingestion=IngestionResult(openinference_trace_id=""),
                error="Source not found for tenant",
            )
        if not source.get("enabled", True):
            return ConnectorSyncResult(
                source_id=source_id,
                tenant_id=tenant_id,
                ingestion=IngestionResult(openinference_trace_id=""),
                error="Source disabled",
            )

        connector = build_connector(source)
        health = connector.health()
        if health.status.value in ("not_configured", "disabled"):
            return ConnectorSyncResult(
                source_id=source_id,
                tenant_id=tenant_id,
                ingestion=IngestionResult(openinference_trace_id=""),
                error=health.message,
            )

        ingestion = self._ingestion.ingest_connector(
            tenant_id=tenant_id,
            source_id=source_id,
            connector=connector,
            limit=int((source.get("config") or {}).get("max_events_per_sync", 50)),
        )

        prospects_created = 0
        prospects_skipped = 0
        campaign_ids: list[str] = []

        if ingest_campaigns and ingestion.events_inserted > 0:
            bridge = StoreIntentRepository(repository=self._repo)
            ingestor = IntentProspectIngestor(
                store=self._store, events=self._events, repository=bridge,
            )
            for eng in self._store.list_engagements(tenant_id=tenant_id, status="active"):
                campaign_ids.append(eng.id)
                result = ingestor.ingest_campaign(
                    tenant_id=tenant_id,
                    engagement_id=eng.id,
                    hours_back=hours_back,
                )
                prospects_created += result.created_count
                prospects_skipped += result.skipped_count

        finished = datetime.now(timezone.utc)
        self._repo.record_ingestion_run(
            SignalIngestionRun(
                id=f"run_{source_id}_{int(started.timestamp())}",
                tenant_id=tenant_id,
                source_id=source_id,
                connector_kind=source.get("connector_kind", ""),
                started_at=started,
                finished_at=finished,
                events_seen=ingestion.events_fetched,
                events_created=ingestion.events_inserted,
                events_deduped=ingestion.events_deduplicated,
                signals_rejected=ingestion.events_rejected,
                prospects_created=prospects_created,
                duration_ms=int((finished - started).total_seconds() * 1000),
                error_state=None,
                trace_id=ingestion.openinference_trace_id,
            )
        )

        return ConnectorSyncResult(
            source_id=source_id,
            tenant_id=tenant_id,
            ingestion=ingestion,
            prospects_created=prospects_created,
            prospects_skipped=prospects_skipped,
            campaign_ids=campaign_ids,
        )

    def sync_all_enabled(self, *, tenant_id: str) -> list[ConnectorSyncResult]:
        results: list[ConnectorSyncResult] = []
        for source in self._repo.list_sources(tenant_id=tenant_id, enabled_only=True):
            try:
                results.append(self.sync_source(tenant_id=tenant_id, source_id=source["id"]))
            except Exception as exc:
                logger.exception("Connector sync failed tenant=%s source=%s", tenant_id, source["id"])
                results.append(ConnectorSyncResult(
                    source_id=source["id"],
                    tenant_id=tenant_id,
                    ingestion=IngestionResult(openinference_trace_id=""),
                    error=str(exc),
                ))
        return results
