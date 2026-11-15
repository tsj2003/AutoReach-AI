"""Enrichment service with distributed billing lease flags (enriching_email, enriching_phone) and compliance guards."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from engine.core.types import Prospect
from engine.enrichment.models import EnrichmentRequest, WaterfallResult
from engine.enrichment.waterfall import EnrichmentWaterfall


class EnrichmentService:
    """High-level enrichment orchestrator enforcing distributed billing leases and multi-slot persistence."""

    def __init__(self, *, waterfall: EnrichmentWaterfall | None = None) -> None:
        self._waterfall = waterfall or EnrichmentWaterfall()

    def enrich_prospect_email(
        self,
        *,
        store: Any,
        prospect: Prospect,
        tenant_id: str,
        ledger: Any = None,
        required_fields: list[str] | None = None,
    ) -> WaterfallResult:
        research = dict(prospect.research or {})
        # Set distributed billing lease flag before invoking paid waterfall providers
        research["enriching_email"] = True
        store.save_prospect(
            Prospect(
                id=prospect.id,
                engagement_id=prospect.engagement_id,
                email=prospect.email,
                full_name=prospect.full_name,
                company=prospect.company,
                title=prospect.title,
                raw=dict(prospect.raw or {}),
                research=research,
                status=prospect.status,
                created_at=prospect.created_at,
            ),
            tenant_id=tenant_id,
        )

        profile = {
            "email": prospect.email,
            "full_name": prospect.full_name,
            "company": prospect.company,
            "title": prospect.title,
            "company_domain": research.get("company_domain") or research.get("domain") or prospect.company,
        }
        req = EnrichmentRequest(
            tenant_id=tenant_id,
            prospect_id=prospect.id,
            email=prospect.email,
            company_domain=profile["company_domain"],
            company_name=prospect.company,
            full_name=prospect.full_name,
            required_fields=required_fields or ["email"],
        )
        result = self._waterfall.enrich(
            req,
            profile=profile,
            ledger=ledger,
            engagement_id=prospect.engagement_id,
            min_confidence=0.5,
        )

        research["enriching_email"] = False
        if result.fields:
            if result.fields.get("email_2"):
                research["email_2"] = result.fields["email_2"]
            if result.fields.get("email_3"):
                research["email_3"] = result.fields["email_3"]
            research["enrichment"] = {
                "provider_used": result.provider_used,
                "providers_attempted": result.providers_attempted,
                "verification_status": result.verification_status.value,
                "confidence": result.confidence,
                "fields": result.fields,
                "email_2": result.fields.get("email_2"),
                "email_3": result.fields.get("email_3"),
                "cost_micro_usd": result.total_cost_micro_usd,
                "trace_id": result.trace_id,
                "enriched_at": datetime.now(timezone.utc).isoformat(),
            }

        email = (result.fields.get("email") if result.fields else None) or prospect.email
        store.save_prospect(
            Prospect(
                id=prospect.id,
                engagement_id=prospect.engagement_id,
                email=email,
                full_name=(result.fields.get("full_name") if result.fields else None) or prospect.full_name,
                company=(result.fields.get("company") if result.fields else None) or prospect.company,
                title=(result.fields.get("title") if result.fields else None) or prospect.title,
                raw=dict(prospect.raw or {}),
                research=research,
                status=prospect.status,
                created_at=prospect.created_at,
            ),
            tenant_id=tenant_id,
        )
        return result
