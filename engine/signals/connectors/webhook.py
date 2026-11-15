"""Webhook signal connector — ingests customer-authorized signed POST payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from engine.signals.connectors.base import ConnectorCapabilities, ConnectorCursor, SignalConnector
from engine.signals.connectors.manual import ManualSignalConnector
from engine.signals.events import ConnectorHealth, ConnectorStatus, SignalFreshness


class WebhookSignalConnector(SignalConnector):
    """Accepts pre-validated webhook payloads queued for ingestion."""

    CONNECTOR_KIND = "webhook"

    def __init__(self, *, source_id: str, webhook_secret: str | None = None) -> None:
        self._source_id = source_id
        self._secret = (webhook_secret or "").strip()
        self._pending: list[dict[str, Any]] = []
        self._manual = ManualSignalConnector(source_id=source_id)

    @property
    def connector_kind(self) -> str:
        return self.CONNECTOR_KIND

    def queue_payload(self, payload: dict[str, Any]) -> None:
        self._pending.append(dict(payload))

    def capabilities(self) -> ConnectorCapabilities:
        configured = bool(self._secret)
        return ConnectorCapabilities(
            connector_kind=self.CONNECTOR_KIND,
            label="Signed webhook",
            freshness=SignalFreshness.REAL_TIME,
            polling_interval_seconds=None,
            supports_webhook=True,
            requires_credentials=True,
            configured=configured,
            supported_signal_types=tuple(self._manual.capabilities().supported_signal_types),
        )

    def health(self) -> ConnectorHealth:
        if not self._secret:
            return ConnectorHealth(
                source_id=self._source_id,
                connector_kind=self.CONNECTOR_KIND,
                status=ConnectorStatus.NOT_CONFIGURED,
                message="NOT CONFIGURED — webhook secret missing",
                freshness=SignalFreshness.REAL_TIME,
            )
        return ConnectorHealth(
            source_id=self._source_id,
            connector_kind=self.CONNECTOR_KIND,
            status=ConnectorStatus.HEALTHY,
            message="Webhook receiver ready",
            freshness=SignalFreshness.REAL_TIME,
        )

    def fetch_events(
        self,
        *,
        tenant_id: str,
        cursor: ConnectorCursor,
        limit: int = 100,
    ) -> tuple[list, ConnectorCursor]:
        batch = self._pending[:limit]
        self._pending = self._pending[limit:]
        events = []
        for payload in batch:
            event = self._manual.normalize_payload(tenant_id=tenant_id, payload=payload)
            if event is not None:
                events.append(event)
        now = datetime.now(timezone.utc)
        return events, ConnectorCursor(
            last_cursor=str(len(batch)),
            last_success_at=now if batch else cursor.last_success_at,
            last_event_at=events[-1].occurred_at if events else cursor.last_event_at,
            error_state=None,
            retry_count=0,
        )
