"""Enrichment provider contracts and result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class VerificationStatus(str, Enum):
    UNKNOWN = "unknown"
    FOUND = "found"
    PROBABLE = "probable"
    VERIFIED = "verified"
    INVALID = "invalid"
    REJECTED = "rejected"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class EnrichmentCapabilities:
    provider_id: str
    label: str
    supports_person: bool
    supports_company: bool
    supports_email_verify: bool
    configured: bool
    cost_micro_usd: int = 0


@dataclass
class EnrichmentRequest:
    tenant_id: str
    prospect_id: str | None
    email: str | None = None
    company_domain: str | None = None
    company_name: str | None = None
    full_name: str | None = None
    required_fields: list[str] = field(default_factory=list)


@dataclass
class EnrichmentProviderResult:
    provider_id: str
    success: bool
    fields: dict[str, Any] = field(default_factory=dict)
    verification_status: VerificationStatus = VerificationStatus.UNKNOWN
    confidence: float = 0.0
    cost_micro_usd: int = 0
    latency_ms: int = 0
    error: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class WaterfallResult:
    job_id: str
    tenant_id: str
    prospect_id: str | None
    providers_attempted: list[str]
    provider_used: str | None
    fields: dict[str, Any]
    verification_status: VerificationStatus
    confidence: float
    total_cost_micro_usd: int
    trace_id: str
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class EnrichmentProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def capabilities(self) -> EnrichmentCapabilities: ...

    def health(self) -> dict[str, Any]: ...

    def enrich(self, request: EnrichmentRequest) -> EnrichmentProviderResult: ...
