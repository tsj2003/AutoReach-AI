"""Intent signal to prospect bridge."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable
from datetime import timezone
from typing import Any

from opentelemetry import trace

from engine.core.protocols import EventSink, Store
from engine.core.types import Event, EventKind, Prospect
from engine.intent.models import IntentIngestionResult, IntentSignal
from engine.intent.repository import DuckDBIntentRepository


class IntentProspectIngestor:
    """Create tenant-scoped prospects from allowed recent intent signals."""

    def __init__(
        self,
        *,
        store: Store,
        events: EventSink,
        repository: DuckDBIntentRepository,
    ) -> None:
        self._store = store
        self._events = events
        self._repository = repository

    def ingest_campaign(
        self,
        *,
        tenant_id: str,
        engagement_id: str,
        hours_back: int = 24,
        limit: int | None = None,
    ) -> IntentIngestionResult:
        """Ingest allowed tenant signals into deterministic campaign prospects."""

        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("intent.ingest_campaign") as span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("campaign.id", engagement_id)
            span.set_attribute("intent.hours_back", hours_back)

            trace_id = format(span.get_span_context().trace_id, "032x")
            engagement = self._store.get_engagement(engagement_id, tenant_id=tenant_id)
            if engagement is None:
                raise PermissionError("engagement not found for tenant")

            allowed_signal_types = self._allowed_signal_types(engagement.metadata)
            span.set_attribute("intent.allowed_signal_types", ",".join(sorted(allowed_signal_types)))
            if not allowed_signal_types:
                return IntentIngestionResult(
                    created_count=0,
                    skipped_count=0,
                    created_prospect_ids=[],
                    openinference_trace_id=trace_id,
                )

            signals = self._repository.get_recent_signals(
                tenant_id=tenant_id,
                hours_back=hours_back,
                signal_types=allowed_signal_types,
                limit=limit,
            )

            created_ids: list[str] = []
            skipped_count = 0
            for signal in signals:
                if signal.signal_type not in allowed_signal_types:
                    skipped_count += 1
                    continue
                prospect_id = self._prospect_id(
                    tenant_id=tenant_id,
                    engagement_id=engagement_id,
                    signal=signal,
                )
                if self._store.get_prospect(prospect_id) is not None:
                    skipped_count += 1
                    continue

                prospect = self._build_prospect(
                    prospect_id=prospect_id,
                    engagement_id=engagement_id,
                    signal=signal,
                    trace_id=trace_id,
                )
                self._store.save_prospect(prospect, tenant_id=tenant_id)
                self._emit_created(
                    tenant_id=tenant_id,
                    engagement_id=engagement_id,
                    prospect=prospect,
                    signal=signal,
                    trace_id=trace_id,
                )
                created_ids.append(prospect_id)

            span.set_attribute("intent.created_count", len(created_ids))
            span.set_attribute("intent.skipped_count", skipped_count)
            return IntentIngestionResult(
                created_count=len(created_ids),
                skipped_count=skipped_count,
                created_prospect_ids=created_ids,
                openinference_trace_id=trace_id,
            )

    @staticmethod
    def _allowed_signal_types(metadata: Any) -> set[str]:
        if not isinstance(metadata, dict):
            return set()
        matrix = metadata.get("signal_matrix")
        if not isinstance(matrix, dict):
            return set()
        raw_types = matrix.get("allowed_signal_types")
        if not isinstance(raw_types, Iterable) or isinstance(raw_types, (str, bytes)):
            return set()
        return {str(signal_type) for signal_type in raw_types if str(signal_type)}

    @staticmethod
    def _prospect_id(*, tenant_id: str, engagement_id: str, signal: IntentSignal) -> str:
        source = "|".join(
            [
                tenant_id,
                engagement_id,
                signal.signal_type,
                signal.company_domain,
                signal.timestamp.isoformat(),
            ]
        )
        return f"p_intent_{hashlib.sha1(source.encode('utf-8')).hexdigest()[:20]}"

    @staticmethod
    def _build_prospect(
        *,
        prospect_id: str,
        engagement_id: str,
        signal: IntentSignal,
        trace_id: str,
    ) -> Prospect:
        payload = dict(signal.payload)
        email = payload.get("email") or payload.get("contact_email")
        company = payload.get("company") or payload.get("company_name") or signal.company_domain
        matched_signal = {
            "signal_type": signal.signal_type,
            "company_domain": signal.company_domain,
            "timestamp": signal.timestamp.isoformat(),
            "summary": IntentProspectIngestor._trigger_summary(signal),
            "openinference_trace_id": trace_id,
        }
        return Prospect(
            id=prospect_id,
            engagement_id=engagement_id,
            email=str(email) if email else None,
            full_name=payload.get("full_name") or payload.get("name"),
            company=str(company) if company else signal.company_domain,
            title=payload.get("title"),
            raw={
                "intent_signal": {
                    "signal_type": signal.signal_type,
                    "company_domain": signal.company_domain,
                    "payload": payload,
                    "timestamp": signal.timestamp.isoformat(),
                    "source": "duckdb.intent_signals",
                    "openinference_trace_id": trace_id,
                }
            },
            research={"matched_intent_signal": matched_signal},
            status="new",
        )

    @staticmethod
    def _trigger_summary(signal: IntentSignal) -> str:
        return f"{signal.signal_type} detected for {signal.company_domain}"

    def _emit_created(
        self,
        *,
        tenant_id: str,
        engagement_id: str,
        prospect: Prospect,
        signal: IntentSignal,
        trace_id: str,
    ) -> None:
        self._events.emit(
            Event(
                id=f"ev_{secrets.token_hex(8)}",
                kind=EventKind.INTENT_PROSPECT_CREATED,
                engagement_id=engagement_id,
                prospect_id=prospect.id,
                payload={
                    "tenant_id": tenant_id,
                    "signal_type": signal.signal_type,
                    "company_domain": signal.company_domain,
                    "openinference_trace_id": trace_id,
                },
            )
        )
