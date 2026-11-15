"""Signal ingestion orchestration — normalize, dedupe, persist."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from opentelemetry import trace

from engine.signals.connectors.base import ConnectorCursor, SignalConnector
from engine.signals.events import CanonicalSignal, SignalEvent
from engine.signals.repository import SignalRepository


@dataclass
class IngestionResult:
    events_fetched: int = 0
    events_inserted: int = 0
    events_deduplicated: int = 0
    events_rejected: int = 0
    canonical_signals: list[CanonicalSignal] = field(default_factory=list)
    openinference_trace_id: str = ""


class SignalIngestionService:
    """Fetch from connectors, persist with idempotency and deduplication."""

    def __init__(self, *, repository: SignalRepository) -> None:
        self._repo = repository

    def ingest_connector(
        self,
        *,
        tenant_id: str,
        source_id: str,
        connector: SignalConnector,
        limit: int = 100,
    ) -> IngestionResult:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("signals.ingest_connector") as span:
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("signal.source_id", source_id)
            span.set_attribute("signal.connector_kind", connector.connector_kind)
            trace_id = format(span.get_span_context().trace_id, "032x")

            cursor = self._repo.get_connector_state(source_id, tenant_id=tenant_id)
            events, new_cursor = connector.fetch_events(
                tenant_id=tenant_id, cursor=cursor, limit=limit,
            )
            result = IngestionResult(
                events_fetched=len(events),
                openinference_trace_id=trace_id,
            )

            for event in events:
                event = SignalEvent(
                    **{
                        **event.__dict__,
                        "trace_id": event.trace_id or trace_id,
                    }
                )
                canonical, is_new = self._repo.upsert_from_event(event)
                if is_new:
                    result.events_inserted += 1
                    result.canonical_signals.append(canonical)
                else:
                    result.events_deduplicated += 1

            self._repo.save_connector_state(source_id, tenant_id, new_cursor)
            span.set_attribute("signal.events_inserted", result.events_inserted)
            return result

    def ingest_events(
        self,
        *,
        tenant_id: str,
        source_id: str,
        events: list[SignalEvent],
    ) -> IngestionResult:
        """Direct ingestion of pre-normalized events (e.g. from API)."""

        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("signals.ingest_events") as span:
            span.set_attribute("tenant.id", tenant_id)
            trace_id = format(span.get_span_context().trace_id, "032x")
            result = IngestionResult(
                events_fetched=len(events),
                openinference_trace_id=trace_id,
            )
            for event in events:
                if event.tenant_id != tenant_id:
                    result.events_rejected += 1
                    continue
                event = SignalEvent(
                    **{**event.__dict__, "source_id": event.source_id or source_id, "trace_id": event.trace_id or trace_id}
                )
                canonical, is_new = self._repo.upsert_from_event(event)
                if is_new:
                    result.events_inserted += 1
                    result.canonical_signals.append(canonical)
                else:
                    result.events_deduplicated += 1
            return result

    def ingest_manual_payloads(
        self,
        *,
        tenant_id: str,
        source_id: str,
        connector: SignalConnector,
        payloads: list[dict],
        trace_id: str | None = None,
    ) -> IngestionResult:
        """Normalize manual payloads and ingest."""

        from engine.signals.connectors.manual import ManualSignalConnector

        if not isinstance(connector, ManualSignalConnector):
            raise TypeError("ingest_manual_payloads requires ManualSignalConnector")

        events: list[SignalEvent] = []
        rejected = 0
        for payload in payloads:
            event = connector.normalize_payload(
                tenant_id=tenant_id,
                payload=payload,
                trace_id=trace_id,
            )
            if event is None:
                rejected += 1
            else:
                events.append(SignalEvent(**{**event.__dict__, "source_id": source_id}))
        result = self.ingest_events(tenant_id=tenant_id, source_id=source_id, events=events)
        result.events_rejected += rejected
        return result
