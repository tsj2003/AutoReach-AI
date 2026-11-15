"""Persist and query signal events in the main Attainly store."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.engine import Engine

from engine.intent.models import IntentSignal
from engine.signals.connectors.base import ConnectorCursor
from engine.signals.dedup import canonical_signal_id, event_to_canonical, merge_into_canonical
from engine.signals.events import CanonicalSignal, SignalEvent, SignalEvidence
from engine.signals.observability import SignalIngestionRun
from engine.storage.sqlite import (
    canonical_signals_table,
    signal_connector_state_table,
    signal_events_table,
    signal_ingestion_runs_table,
    signal_sources_table,
    _coerce_json,
    _ensure_utc,
)


class SignalRepository:
    """Tenant-scoped signal persistence backed by SQLAlchemy tables."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save_source(
        self,
        *,
        source_id: str,
        tenant_id: str,
        connector_kind: str,
        name: str,
        config: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        now = datetime.now(timezone.utc)
        values = {
            "id": source_id,
            "tenant_id": tenant_id,
            "connector_kind": connector_kind,
            "name": name,
            "config_json": config or {},
            "enabled": enabled,
            "created_at": now,
            "updated_at": now,
        }
        with self._engine.begin() as conn:
            existing = conn.execute(
                select(signal_sources_table).where(signal_sources_table.c.id == source_id)
            ).first()
            if existing:
                # P0: refuse cross-tenant overwrite of connector config
                if existing.tenant_id != tenant_id:
                    raise PermissionError("signal source belongs to another tenant")
                conn.execute(
                    signal_sources_table.update()
                    .where(
                        signal_sources_table.c.id == source_id,
                        signal_sources_table.c.tenant_id == tenant_id,
                    )
                    .values(**{k: v for k, v in values.items() if k not in ("created_at", "id")})
                )
            else:
                conn.execute(signal_sources_table.insert().values(**values))

    def list_sources(
        self,
        *,
        tenant_id: str,
        enabled_only: bool = False,
    ) -> list[dict[str, Any]]:
        stmt = select(signal_sources_table).where(signal_sources_table.c.tenant_id == tenant_id)
        if enabled_only:
            stmt = stmt.where(signal_sources_table.c.enabled.is_(True))
        stmt = stmt.order_by(signal_sources_table.c.created_at.desc())
        with self._engine.begin() as conn:
            rows = conn.execute(stmt).all()
        return [self._row_to_source(row) for row in rows]

    def list_tenant_ids_with_enabled_sources(self) -> list[str]:
        with self._engine.begin() as conn:
            rows = conn.execute(
                select(signal_sources_table.c.tenant_id)
                .where(signal_sources_table.c.enabled.is_(True))
                .distinct()
            ).all()
        return sorted({r.tenant_id for r in rows})

    def update_source(
        self,
        *,
        source_id: str,
        tenant_id: str,
        name: str | None = None,
        config: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        source = self.get_source(source_id, tenant_id=tenant_id)
        if source is None:
            return None
        if name is not None:
            source["name"] = name
        if config is not None:
            source["config"] = config
        if enabled is not None:
            source["enabled"] = enabled
        self.save_source(
            source_id=source_id,
            tenant_id=tenant_id,
            connector_kind=source["connector_kind"],
            name=source["name"],
            config=source["config"],
            enabled=source["enabled"],
        )
        return self.get_source(source_id, tenant_id=tenant_id)

    @staticmethod
    def _row_to_source(row: Any) -> dict[str, Any]:
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "connector_kind": row.connector_kind,
            "name": row.name,
            "config": _coerce_json(row.config_json),
            "enabled": bool(row.enabled),
            "created_at": _ensure_utc(row.created_at),
            "updated_at": _ensure_utc(row.updated_at),
        }

    def get_source(self, source_id: str, *, tenant_id: str) -> dict[str, Any] | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(signal_sources_table).where(
                    signal_sources_table.c.id == source_id,
                    signal_sources_table.c.tenant_id == tenant_id,
                )
            ).first()
        if not row:
            return None
        return self._row_to_source(row)

    def get_source_tenant_id(self, source_id: str) -> str | None:
        """Resolve tenant for webhook ingress — never trust tenant_id from payload."""
        with self._engine.begin() as conn:
            row = conn.execute(
                select(signal_sources_table.c.tenant_id).where(
                    signal_sources_table.c.id == source_id,
                )
            ).first()
        return row.tenant_id if row else None

    def save_connector_state(self, source_id: str, tenant_id: str, cursor: ConnectorCursor) -> None:
        if self.get_source(source_id, tenant_id=tenant_id) is None:
            raise PermissionError("signal source not found for tenant")
        now = datetime.now(timezone.utc)
        values = {
            "source_id": source_id,
            "tenant_id": tenant_id,
            "last_cursor": cursor.last_cursor,
            "last_success_at": cursor.last_success_at,
            "last_event_at": cursor.last_event_at,
            "error_state": cursor.error_state,
            "retry_count": cursor.retry_count,
            "updated_at": now,
        }
        with self._engine.begin() as conn:
            existing = conn.execute(
                select(signal_connector_state_table.c.source_id).where(
                    signal_connector_state_table.c.source_id == source_id,
                    signal_connector_state_table.c.tenant_id == tenant_id,
                )
            ).first()
            if existing:
                conn.execute(
                    signal_connector_state_table.update()
                    .where(
                        signal_connector_state_table.c.source_id == source_id,
                        signal_connector_state_table.c.tenant_id == tenant_id,
                    )
                    .values(**{k: v for k, v in values.items() if k != "source_id"})
                )
            else:
                conn.execute(signal_connector_state_table.insert().values(**values))

    def get_connector_state(self, source_id: str, *, tenant_id: str) -> ConnectorCursor:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(signal_connector_state_table).where(
                    signal_connector_state_table.c.source_id == source_id,
                    signal_connector_state_table.c.tenant_id == tenant_id,
                )
            ).first()
        if not row:
            return ConnectorCursor()
        return ConnectorCursor(
            last_cursor=row.last_cursor,
            last_success_at=_ensure_utc(row.last_success_at),
            last_event_at=_ensure_utc(row.last_event_at),
            error_state=row.error_state,
            retry_count=int(row.retry_count or 0),
        )

    def event_exists(self, event_id: str, *, tenant_id: str) -> bool:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(signal_events_table.c.id).where(
                    signal_events_table.c.id == event_id,
                    signal_events_table.c.tenant_id == tenant_id,
                )
            ).first()
        return row is not None

    def save_event(self, event: SignalEvent) -> bool:
        """Persist event idempotently. Returns True if newly inserted."""

        if self.event_exists(event.id, tenant_id=event.tenant_id):
            return False
        values = {
            "id": event.id,
            "tenant_id": event.tenant_id,
            "source_id": event.source_id,
            "source_event_id": event.source_event_id,
            "signal_type": event.signal_type,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "company_domain": event.company_domain,
            "company_name": event.company_name,
            "person_identifier": event.person_identifier,
            "occurred_at": event.occurred_at,
            "observed_at": event.observed_at,
            "confidence": str(event.confidence),
            "evidence_json": event.evidence.as_dict(),
            "source_url": event.source_url,
            "raw_payload_json": event.raw_payload,
            "metadata_json": event.metadata,
            "trace_id": event.trace_id,
            "schema_version": event.schema_version,
            "freshness": event.freshness.value,
            "canonical_signal_id": event.canonical_signal_id,
            "created_at": datetime.now(timezone.utc),
        }
        with self._engine.begin() as conn:
            conn.execute(signal_events_table.insert().values(**values))
        return True

    def get_canonical(self, canonical_id: str, *, tenant_id: str) -> CanonicalSignal | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(canonical_signals_table).where(
                    canonical_signals_table.c.id == canonical_id,
                    canonical_signals_table.c.tenant_id == tenant_id,
                )
            ).first()
        return self._row_to_canonical(row) if row else None

    def save_canonical(self, canonical: CanonicalSignal) -> None:
        values = {
            "id": canonical.id,
            "tenant_id": canonical.tenant_id,
            "signal_type": canonical.signal_type,
            "company_domain": canonical.company_domain,
            "entity_type": canonical.entity_type,
            "entity_id": canonical.entity_id,
            "company_name": canonical.company_name,
            "occurred_at": canonical.occurred_at,
            "confidence": str(canonical.confidence),
            "evidence_json": canonical.evidence.as_dict(),
            "source_count": canonical.source_count,
            "source_event_ids_json": list(canonical.source_event_ids),
            "first_observed_at": canonical.first_observed_at,
            "last_observed_at": canonical.last_observed_at,
            "metadata_json": canonical.metadata,
            "updated_at": datetime.now(timezone.utc),
        }
        with self._engine.begin() as conn:
            existing = conn.execute(
                select(canonical_signals_table.c.id).where(
                    canonical_signals_table.c.id == canonical.id,
                    canonical_signals_table.c.tenant_id == canonical.tenant_id,
                )
            ).first()
            if existing:
                conn.execute(
                    canonical_signals_table.update()
                    .where(
                        canonical_signals_table.c.id == canonical.id,
                        canonical_signals_table.c.tenant_id == canonical.tenant_id,
                    )
                    .values(**values)
                )
            else:
                conn.execute(
                    canonical_signals_table.insert().values(
                        **values,
                        created_at=datetime.now(timezone.utc),
                    )
                )

    def upsert_from_event(self, event: SignalEvent) -> tuple[CanonicalSignal, bool]:
        """Dedup event into canonical signal. Returns (canonical, event_was_new)."""

        cid = canonical_signal_id(
            tenant_id=event.tenant_id,
            signal_type=event.signal_type,
            company_domain=event.company_domain,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            occurred_at=event.occurred_at,
        )
        event_with_cid = SignalEvent(
            **{**event.__dict__, "canonical_signal_id": cid}
        )
        is_new = self.save_event(event_with_cid)
        existing = self.get_canonical(cid, tenant_id=event.tenant_id)
        if existing and not is_new:
            merged = merge_into_canonical(existing, event_with_cid)
            self.save_canonical(merged)
            return merged, False
        if existing:
            canonical = merge_into_canonical(existing, event_with_cid)
        else:
            canonical = event_to_canonical(event_with_cid)
        self.save_canonical(canonical)
        return canonical, is_new

    def list_recent_as_intent_signals(
        self,
        *,
        tenant_id: str,
        hours_back: int,
        signal_types: Iterable[str] | None = None,
        limit: Optional[int] = None,
    ) -> list[IntentSignal]:
        """Bridge to existing IntentProspectIngestor via canonical signals."""

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        stmt = (
            select(canonical_signals_table)
            .where(
                canonical_signals_table.c.tenant_id == tenant_id,
                canonical_signals_table.c.last_observed_at >= cutoff,
            )
            .order_by(canonical_signals_table.c.last_observed_at.desc())
        )
        normalized_types = sorted({str(t) for t in signal_types or []})
        if normalized_types:
            stmt = stmt.where(canonical_signals_table.c.signal_type.in_(normalized_types))
        if limit is not None:
            stmt = stmt.limit(int(limit))

        with self._engine.begin() as conn:
            rows = conn.execute(stmt).all()

        return [self._canonical_to_intent(row) for row in rows]

    @staticmethod
    def _evidence_from_row(row_evidence: Any) -> SignalEvidence:
        data = _coerce_json(row_evidence)
        return SignalEvidence(
            summary=str(data.get("summary") or ""),
            source_url=data.get("source_url"),
            matched_reason=data.get("matched_reason"),
            raw_excerpt=data.get("raw_excerpt"),
        )

    def _row_to_canonical(self, row: Any) -> CanonicalSignal:
        evidence = self._evidence_from_row(row.evidence_json)
        source_raw = row.source_event_ids_json
        if isinstance(source_raw, list):
            ids = tuple(str(x) for x in source_raw)
        elif isinstance(source_raw, str):
            try:
                parsed = json.loads(source_raw)
                ids = tuple(str(x) for x in parsed) if isinstance(parsed, list) else ()
            except json.JSONDecodeError:
                ids = ()
        else:
            ids = ()
        return CanonicalSignal(
            id=row.id,
            tenant_id=row.tenant_id,
            signal_type=row.signal_type,
            company_domain=row.company_domain,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            company_name=row.company_name,
            occurred_at=_ensure_utc(row.occurred_at),
            confidence=float(row.confidence),
            evidence=evidence,
            source_count=int(row.source_count or 1),
            source_event_ids=ids,
            first_observed_at=_ensure_utc(row.first_observed_at),
            last_observed_at=_ensure_utc(row.last_observed_at),
            metadata=_coerce_json(row.metadata_json),
        )

    def _canonical_to_intent(self, row: Any) -> IntentSignal:
        evidence = self._evidence_from_row(row.evidence_json)
        metadata = _coerce_json(row.metadata_json)
        payload = {
            "company": row.company_name or metadata.get("company"),
            "summary": evidence.summary,
            "source_url": evidence.source_url,
            "matched_reason": evidence.matched_reason,
            "confidence": float(row.confidence),
            "source_count": int(row.source_count or 1),
            **{k: v for k, v in metadata.items() if k not in ("connector",)},
        }
        return IntentSignal(
            tenant_id=row.tenant_id,
            signal_type=row.signal_type,
            company_domain=row.company_domain,
            payload=payload,
            timestamp=_ensure_utc(row.last_observed_at),
        )

    def record_ingestion_run(self, run: SignalIngestionRun) -> None:
        values = {
            "id": run.id,
            "tenant_id": run.tenant_id,
            "source_id": run.source_id,
            "connector_kind": run.connector_kind,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "events_seen": run.events_seen,
            "events_created": run.events_created,
            "events_deduped": run.events_deduped,
            "signals_rejected": run.signals_rejected,
            "prospects_created": run.prospects_created,
            "duration_ms": run.duration_ms,
            "error_state": run.error_state,
            "trace_id": run.trace_id,
            "created_at": datetime.now(timezone.utc),
        }
        with self._engine.begin() as conn:
            conn.execute(signal_ingestion_runs_table.insert().values(**values))

    def list_ingestion_runs(
        self,
        *,
        tenant_id: str,
        source_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(signal_ingestion_runs_table)
            .where(signal_ingestion_runs_table.c.tenant_id == tenant_id)
            .order_by(signal_ingestion_runs_table.c.started_at.desc())
            .limit(limit)
        )
        if source_id:
            stmt = stmt.where(signal_ingestion_runs_table.c.source_id == source_id)
        with self._engine.begin() as conn:
            rows = conn.execute(stmt).all()
        return [
            {
                "id": r.id,
                "tenant_id": r.tenant_id,
                "source_id": r.source_id,
                "connector_kind": r.connector_kind,
                "started_at": _ensure_utc(r.started_at).isoformat(),
                "finished_at": _ensure_utc(r.finished_at).isoformat(),
                "events_seen": r.events_seen,
                "events_created": r.events_created,
                "events_deduped": r.events_deduped,
                "signals_rejected": r.signals_rejected,
                "prospects_created": r.prospects_created,
                "duration_ms": r.duration_ms,
                "error_state": r.error_state,
                "trace_id": r.trace_id,
            }
            for r in rows
        ]

    def count_events(self, *, tenant_id: str, source_id: str | None = None) -> int:
        stmt = select(signal_events_table.c.id).where(signal_events_table.c.tenant_id == tenant_id)
        if source_id:
            stmt = stmt.where(signal_events_table.c.source_id == source_id)
        with self._engine.begin() as conn:
            rows = conn.execute(stmt).all()
        return len(rows)
