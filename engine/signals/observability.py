"""Ingestion run observability records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SignalIngestionRun:
    id: str
    tenant_id: str
    source_id: str
    connector_kind: str
    started_at: datetime
    finished_at: datetime
    events_seen: int
    events_created: int
    events_deduped: int
    signals_rejected: int
    prospects_created: int
    duration_ms: int
    error_state: str | None
    trace_id: str | None
