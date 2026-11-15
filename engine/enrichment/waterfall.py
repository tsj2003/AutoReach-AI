"""Enrichment waterfall orchestrator."""

from __future__ import annotations

import secrets
from typing import Any

from opentelemetry import trace

from engine.core.types import CostEntry
from engine.enrichment.models import (
    EnrichmentProvider,
    EnrichmentRequest,
    VerificationStatus,
    WaterfallResult,
)
from engine.enrichment.providers import DnsMxProvider, HunterProvider, InHousePermutationSmtpProvider, NotConfiguredProvider, ProfileDataProvider, build_default_providers


class EnrichmentWaterfall:
    """Try providers in order until required confidence is met."""

    def __init__(self, *, providers: list[EnrichmentProvider] | None = None) -> None:
        self._providers: list[EnrichmentProvider] = providers or build_default_providers()

    def list_providers(self) -> list[dict[str, Any]]:
        return [
            {
                **p.capabilities().__dict__,
                "health": p.health(),
            }
            for p in self._providers
        ]

    def enrich(
        self,
        request: EnrichmentRequest,
        *,
        profile: dict[str, Any] | None = None,
        ledger=None,
        engagement_id: str | None = None,
        min_confidence: float = 0.5,
    ) -> WaterfallResult:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("enrichment.waterfall") as span:
            span.set_attribute("tenant.id", request.tenant_id)
            trace_id = format(span.get_span_context().trace_id, "032x")
            job_id = f"enr_{secrets.token_hex(8)}"
            attempted: list[str] = []
            merged_fields: dict[str, Any] = {}
            best_status = VerificationStatus.UNKNOWN
            best_confidence = 0.0
            provider_used: str | None = None
            total_cost = 0

            for provider in self._providers:
                caps = provider.capabilities()
                if not caps.configured:
                    continue
                attempted.append(provider.provider_id)
                if isinstance(provider, ProfileDataProvider):
                    result = provider.enrich(request, profile=profile)
                else:
                    result = provider.enrich(request)

                total_cost += result.cost_micro_usd
                if result.success:
                    merged_fields.update(result.fields)
                    if result.confidence >= best_confidence:
                        best_confidence = result.confidence
                        best_status = result.verification_status
                        provider_used = provider.provider_id

                if best_confidence >= min_confidence and _fields_satisfied(merged_fields, request.required_fields):
                    break

            if ledger and engagement_id and total_cost > 0:
                ledger.debit(CostEntry(
                    id=f"cost_{secrets.token_hex(6)}",
                    engagement_id=engagement_id,
                    category="enrichment",
                    amount_cents=max(1, total_cost // 10_000),
                    metadata={"cost_micro_usd": total_cost, "providers": attempted, "trace_id": trace_id},
                ))

            return WaterfallResult(
                job_id=job_id,
                tenant_id=request.tenant_id,
                prospect_id=request.prospect_id,
                providers_attempted=attempted,
                provider_used=provider_used,
                fields=merged_fields,
                verification_status=best_status,
                confidence=best_confidence,
                total_cost_micro_usd=total_cost,
                trace_id=trace_id,
            )


def _fields_satisfied(fields: dict[str, Any], required: list[str]) -> bool:
    if not required:
        return bool(fields)
    return all(fields.get(k) for k in required)
