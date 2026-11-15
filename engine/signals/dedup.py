"""Deterministic signal deduplication."""

from __future__ import annotations

import hashlib
from datetime import datetime

from engine.signals.events import CanonicalSignal, SignalEvent, SignalEvidence


def canonical_signal_id(
    *,
    tenant_id: str,
    signal_type: str,
    company_domain: str,
    entity_type: str,
    entity_id: str | None,
    occurred_at: datetime,
) -> str:
    """Deterministic ID for a real-world signal event."""

    day = occurred_at.strftime("%Y-%m-%d")
    entity_key = entity_id or company_domain
    digest = hashlib.sha256(
        f"{tenant_id}|{signal_type}|{company_domain}|{entity_type}|{entity_key}|{day}".encode()
    ).hexdigest()
    return f"cs_{digest[:28]}"


def merge_evidence(existing: SignalEvidence, incoming: SignalEvidence) -> SignalEvidence:
    """Prefer richer evidence when deduplicating."""

    summary = existing.summary if len(existing.summary) >= len(incoming.summary) else incoming.summary
    source_url = existing.source_url or incoming.source_url
    matched_reason = existing.matched_reason or incoming.matched_reason
    raw_excerpt = existing.raw_excerpt or incoming.raw_excerpt
    return SignalEvidence(
        summary=summary,
        source_url=source_url,
        matched_reason=matched_reason,
        raw_excerpt=raw_excerpt,
    )


def merge_into_canonical(
    existing: CanonicalSignal,
    event: SignalEvent,
) -> CanonicalSignal:
    """Merge a new source event into an existing canonical signal."""

    merged_evidence = merge_evidence(existing.evidence, event.evidence)
    source_ids = tuple(sorted(set(existing.source_event_ids + (event.id,))))
    return CanonicalSignal(
        id=existing.id,
        tenant_id=existing.tenant_id,
        signal_type=existing.signal_type,
        company_domain=existing.company_domain,
        entity_type=existing.entity_type,
        entity_id=existing.entity_id,
        company_name=existing.company_name or event.company_name,
        occurred_at=min(existing.occurred_at, event.occurred_at),
        confidence=max(existing.confidence, event.confidence),
        evidence=merged_evidence,
        source_count=len(source_ids),
        source_event_ids=source_ids,
        first_observed_at=min(existing.first_observed_at, event.observed_at),
        last_observed_at=max(existing.last_observed_at, event.observed_at),
        metadata={**existing.metadata, **event.metadata},
    )


def event_to_canonical(event: SignalEvent) -> CanonicalSignal:
    """Create a new canonical signal from a single source event."""

    cid = canonical_signal_id(
        tenant_id=event.tenant_id,
        signal_type=event.signal_type,
        company_domain=event.company_domain,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        occurred_at=event.occurred_at,
    )
    return CanonicalSignal(
        id=cid,
        tenant_id=event.tenant_id,
        signal_type=event.signal_type,
        company_domain=event.company_domain,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        company_name=event.company_name,
        occurred_at=event.occurred_at,
        confidence=event.confidence,
        evidence=event.evidence,
        source_count=1,
        source_event_ids=(event.id,),
        first_observed_at=event.observed_at,
        last_observed_at=event.observed_at,
        metadata=dict(event.metadata),
    )
