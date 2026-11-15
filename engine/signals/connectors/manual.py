"""Manual/API signal connector — tenant-submitted signals with real persistence.

This is NOT a fake provider. It accepts explicitly submitted events (demo,
controlled pilot, webhook relay) and normalizes them through the real ingestion
pipeline with registry validation and deduplication.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from engine.signals.connectors.base import ConnectorCapabilities, ConnectorCursor, SignalConnector
from engine.signals.events import ConnectorHealth, ConnectorStatus, SignalEvidence, SignalEvent, SignalFreshness
from engine.signals.registry import get_signal_registry


class ManualSignalConnector(SignalConnector):
    """Accept pre-normalized signal payloads submitted via API or worker."""

    CONNECTOR_KIND = "manual"

    def __init__(
        self,
        *,
        source_id: str,
        pending_events: list[dict[str, Any]] | None = None,
    ) -> None:
        self._source_id = source_id
        self._pending: list[dict[str, Any]] = list(pending_events or [])
        self._registry = get_signal_registry()

    @property
    def connector_kind(self) -> str:
        return self.CONNECTOR_KIND

    def submit(self, payload: dict[str, Any]) -> None:
        """Queue one raw payload for the next fetch_events call."""

        self._pending.append(dict(payload))

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector_kind=self.CONNECTOR_KIND,
            label="Manual / API",
            freshness=SignalFreshness.MANUAL,
            polling_interval_seconds=None,
            supports_webhook=True,
            requires_credentials=False,
            configured=True,
            supported_signal_types=tuple(self._registry.list_keys()),
        )

    def health(self) -> ConnectorHealth:
        return ConnectorHealth(
            source_id=self._source_id,
            connector_kind=self.CONNECTOR_KIND,
            status=ConnectorStatus.HEALTHY,
            message="Manual connector ready",
            freshness=SignalFreshness.MANUAL,
        )

    def normalize_payload(
        self,
        *,
        tenant_id: str,
        payload: dict[str, Any],
        observed_at: datetime | None = None,
        trace_id: str | None = None,
    ) -> SignalEvent | None:
        """Convert a submitted payload to a SignalEvent, or None if invalid."""

        raw_type = str(payload.get("signal_type", "")).strip()
        canonical = self._registry.normalize(raw_type)
        if canonical is None:
            return None

        domain = str(payload.get("company_domain", "")).strip().lower()
        if not domain or "." not in domain:
            return None

        now = observed_at or datetime.now(timezone.utc)
        occurred_raw = payload.get("occurred_at")
        if isinstance(occurred_raw, datetime):
            occurred_at = occurred_raw if occurred_raw.tzinfo else occurred_raw.replace(tzinfo=timezone.utc)
        elif isinstance(occurred_raw, str) and occurred_raw.strip():
            occurred_at = datetime.fromisoformat(occurred_raw.replace("Z", "+00:00"))
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        else:
            occurred_at = now

        evidence_data = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        summary = str(
            evidence_data.get("summary")
            or payload.get("summary")
            or f"{canonical.replace('_', ' ')} at {domain}"
        ).strip()

        source_event_id = str(payload.get("source_event_id") or "").strip()
        if not source_event_id:
            stable_key = f"{tenant_id}|{canonical}|{domain}|{summary[:120]}"
            source_event_id = hashlib.sha256(stable_key.encode()).hexdigest()[:24]

        event_id = hashlib.sha256(
            f"{tenant_id}|{self._source_id}|{source_event_id}".encode()
        ).hexdigest()[:32]

        evidence = SignalEvidence(
            summary=summary[:500],
            source_url=evidence_data.get("source_url") or payload.get("source_url"),
            matched_reason=evidence_data.get("matched_reason") or payload.get("matched_reason"),
            raw_excerpt=(str(evidence_data.get("raw_excerpt") or "")[:1000] or None),
        )

        confidence_raw = payload.get("confidence", 0.85)
        try:
            confidence = max(0.0, min(1.0, float(confidence_raw)))
        except (TypeError, ValueError):
            confidence = 0.85

        raw_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        if not raw_payload:
            raw_payload = {k: v for k, v in payload.items() if k not in {
                "signal_type", "company_domain", "occurred_at", "source_event_id",
                "evidence", "summary", "source_url", "confidence", "company_name",
            }}

        return SignalEvent(
            id=event_id,
            tenant_id=tenant_id,
            source_id=self._source_id,
            source_event_id=source_event_id,
            signal_type=canonical,
            entity_type=str(payload.get("entity_type") or "company"),
            entity_id=payload.get("entity_id"),
            company_domain=domain,
            company_name=payload.get("company_name"),
            person_identifier=payload.get("person_identifier"),
            occurred_at=occurred_at,
            observed_at=now,
            confidence=confidence,
            evidence=evidence,
            source_url=evidence.source_url,
            raw_payload=raw_payload,
            metadata={"connector": self.CONNECTOR_KIND, **raw_payload},
            trace_id=trace_id,
            freshness=SignalFreshness.MANUAL,
        )

    def fetch_events(
        self,
        *,
        tenant_id: str,
        cursor: ConnectorCursor,
        limit: int = 100,
    ) -> tuple[list[SignalEvent], ConnectorCursor]:
        batch = self._pending[:limit]
        self._pending = self._pending[limit:]
        events: list[SignalEvent] = []
        for payload in batch:
            event = self.normalize_payload(tenant_id=tenant_id, payload=payload)
            if event is not None:
                events.append(event)
        new_cursor = ConnectorCursor(
            last_cursor=str(len(events)),
            last_success_at=datetime.now(timezone.utc),
            last_event_at=events[-1].occurred_at if events else cursor.last_event_at,
            error_state=None,
            retry_count=0,
        )
        return events, new_cursor
