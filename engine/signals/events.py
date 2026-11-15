"""Normalized signal event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


SCHEMA_VERSION = "1.0.0"


class SignalFreshness(str, Enum):
    """Honest freshness classification — do not call polling 'real-time'."""

    REAL_TIME = "real_time"  # webhook / event stream
    NEAR_REAL_TIME = "near_real_time"  # documented polling interval
    DAILY = "daily"
    MANUAL = "manual"  # operator/API submitted


class ConnectorStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass(frozen=True)
class ConnectorHealth:
    source_id: str
    connector_kind: str
    status: ConnectorStatus
    message: str
    last_success_at: datetime | None = None
    last_event_at: datetime | None = None
    freshness: SignalFreshness = SignalFreshness.MANUAL


@dataclass(frozen=True)
class SignalEvidence:
    """Structured evidence preserved for every actionable signal."""

    summary: str
    source_url: str | None = None
    matched_reason: str | None = None
    raw_excerpt: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "source_url": self.source_url,
            "matched_reason": self.matched_reason,
            "raw_excerpt": self.raw_excerpt,
        }


@dataclass(frozen=True)
class SignalEvent:
    """Provider-normalized event before deduplication."""

    id: str
    tenant_id: str
    source_id: str
    source_event_id: str
    signal_type: str  # canonical registry key
    entity_type: str  # company | person | account
    entity_id: str | None
    company_domain: str
    company_name: str | None
    person_identifier: str | None
    occurred_at: datetime
    observed_at: datetime
    confidence: float  # 0.0–1.0
    evidence: SignalEvidence
    source_url: str | None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    schema_version: str = SCHEMA_VERSION
    freshness: SignalFreshness = SignalFreshness.MANUAL
    canonical_signal_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "source_id": self.source_id,
            "source_event_id": self.source_event_id,
            "signal_type": self.signal_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "company_domain": self.company_domain,
            "company_name": self.company_name,
            "person_identifier": self.person_identifier,
            "occurred_at": self.occurred_at.isoformat(),
            "observed_at": self.observed_at.isoformat(),
            "confidence": self.confidence,
            "evidence": self.evidence.as_dict(),
            "source_url": self.source_url,
            "raw_payload": self.raw_payload,
            "metadata": self.metadata,
            "trace_id": self.trace_id,
            "schema_version": self.schema_version,
            "freshness": self.freshness.value,
            "canonical_signal_id": self.canonical_signal_id,
        }


@dataclass(frozen=True)
class CanonicalSignal:
    """Deduplicated real-world signal with source provenance."""

    id: str
    tenant_id: str
    signal_type: str
    company_domain: str
    entity_type: str
    entity_id: str | None
    company_name: str | None
    occurred_at: datetime
    confidence: float
    evidence: SignalEvidence
    source_count: int
    source_event_ids: tuple[str, ...]
    first_observed_at: datetime
    last_observed_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "signal_type": self.signal_type,
            "company_domain": self.company_domain,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "company_name": self.company_name,
            "occurred_at": self.occurred_at.isoformat(),
            "confidence": self.confidence,
            "evidence": self.evidence.as_dict(),
            "source_count": self.source_count,
            "source_event_ids": list(self.source_event_ids),
            "first_observed_at": self.first_observed_at.isoformat(),
            "last_observed_at": self.last_observed_at.isoformat(),
            "metadata": self.metadata,
        }
