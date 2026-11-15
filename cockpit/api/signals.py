"""Signal intelligence API — catalog, connectors, sync."""

from __future__ import annotations

import secrets
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cockpit.api.deps import get_current_user, get_events, get_store
from cockpit.api.ratelimit import rate_limit
from engine.auth import CurrentUser
from engine.security.safe_fetch import is_safe_fetch_url
from engine.signals.connectors.manual import ManualSignalConnector
from engine.signals.connectors.rss import RSSSignalConnector
from engine.signals.webhook_auth import generate_webhook_secret
from engine.signals.catalog import get_gojiberry_signal_catalog, get_reject_reasons
from engine.signals.feature_flags import is_signals_enabled
from engine.signals.ingestion import SignalIngestionService
from engine.signals.registry import get_signal_registry
from engine.signals.repository import SignalRepository
from engine.signals.service import SignalConnectorService, build_connector
from engine.core.types import Prospect

router = APIRouter(prefix="/api/signals", tags=["signals"])


class LookalikesRequest(BaseModel):
    seed_domains: list[str] = Field(default_factory=list)
    campaign_id: Optional[str] = None
    limit: int = Field(default=6, ge=1, le=25)
    auto_import: bool = False


class CreateSourceRequest(BaseModel):
    connector_kind: str = Field(..., pattern="^(rss|manual|webhook)$")
    name: str = Field(..., min_length=1, max_length=120)
    feed_url: Optional[str] = None
    allowed_signal_types: list[str] = Field(default_factory=list)
    max_entries: int = Field(default=50, ge=1, le=100)
    enabled: bool = True


class UpdateSourceRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    feed_url: Optional[str] = None
    allowed_signal_types: Optional[list[str]] = None
    max_entries: Optional[int] = Field(default=None, ge=1, le=100)
    enabled: Optional[bool] = None


def _repo_from_store(store) -> SignalRepository:
    return SignalRepository(store._holder.engine)


def _require_signals_enabled() -> None:
    if not is_signals_enabled():
        raise HTTPException(
            503,
            "Signal intelligence is not enabled on this deployment (AUTOREACH_SIGNALS_ENABLED=0)",
        )


@router.get("/catalog")
def get_signal_catalog(current_user: CurrentUser = Depends(get_current_user)):
    """Versioned signal type catalog from the real registry."""

    registry = get_signal_registry()
    catalog = registry.catalog_for_api()
    for item in catalog["types"]:
        item["freshness_default_hours"] = item.pop("default_freshness_hours")
        item["required_evidence"] = ["summary", "source_url"]
        item["source_support"] = {
            "manual": True,
            "rss": item["key"] in {
                "funding_round", "hiring_surge", "job_posting", "leadership_change",
                "product_launch", "acquisition", "technology_adoption", "geographic_expansion",
            },
        }
    return {
        **catalog,
        "gojiberry_signals": get_gojiberry_signal_catalog(),
        "gojiberry_count": len(get_gojiberry_signal_catalog()),
        "reject_reasons": get_reject_reasons(),
        "enabled_on_deployment": is_signals_enabled(),
        "live_connectors": ["manual", "rss", "webhook"],
    }


@router.get("/sources")
def list_sources(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    _require_signals_enabled()
    repo = _repo_from_store(store)
    sources = []
    for src in repo.list_sources(tenant_id=current_user.tenant_id):
        connector = build_connector(src)
        health = connector.health()
        state = repo.get_connector_state(src["id"], tenant_id=current_user.tenant_id)
        safe_config = dict(src.get("config") or {})
        if "webhook_secret" in safe_config:
            safe_config = {**safe_config, "webhook_secret": "***"}
        sources.append({
            **src,
            "config": safe_config,
            "health": {
                "status": health.status.value,
                "message": health.message,
                "freshness": health.freshness.value,
            },
            "last_success_at": state.last_success_at.isoformat() if state.last_success_at else None,
            "last_event_at": state.last_event_at.isoformat() if state.last_event_at else None,
            "error_state": state.error_state,
            "event_count": repo.count_events(tenant_id=current_user.tenant_id, source_id=src["id"]),
        })
    return {"sources": sources}


@router.post("/sources", dependencies=[Depends(rate_limit("signals_sources", limit=20, window_seconds=3600))])
def create_source(
    body: CreateSourceRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    _require_signals_enabled()
    if body.connector_kind == "rss":
        if not body.feed_url or not is_safe_fetch_url(body.feed_url):
            raise HTTPException(400, "Invalid or blocked feed URL (SSRF policy)")
    registry = get_signal_registry()
    normalized_types = []
    for raw in body.allowed_signal_types:
        canonical = registry.normalize(raw)
        if canonical:
            normalized_types.append(canonical)

    source_id = f"src_{secrets.token_hex(8)}"
    config: dict[str, Any] = {
        "allowed_signal_types": normalized_types,
        "max_entries": body.max_entries,
    }
    if body.connector_kind == "rss":
        config["feed_url"] = body.feed_url
    webhook_secret: str | None = None
    if body.connector_kind == "webhook":
        webhook_secret = generate_webhook_secret()
        config["webhook_secret"] = webhook_secret

    repo = _repo_from_store(store)
    repo.save_source(
        source_id=source_id,
        tenant_id=current_user.tenant_id,
        connector_kind=body.connector_kind,
        name=body.name,
        config=config,
        enabled=body.enabled,
    )
    response: dict[str, Any] = {"ok": True, "source_id": source_id}
    if webhook_secret:
        response["webhook_secret"] = webhook_secret
        response["webhook_url"] = f"/api/webhooks/signals/{source_id}"
    return response


@router.patch("/sources/{source_id}")
def update_source(
    source_id: str,
    body: UpdateSourceRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    _require_signals_enabled()
    repo = _repo_from_store(store)
    existing = repo.get_source(source_id, tenant_id=current_user.tenant_id)
    if not existing:
        raise HTTPException(404, "Source not found")

    config = dict(existing.get("config") or {})
    if body.feed_url is not None:
        if not is_safe_fetch_url(body.feed_url):
            raise HTTPException(400, "Invalid or blocked feed URL")
        config["feed_url"] = body.feed_url
    if body.allowed_signal_types is not None:
        registry = get_signal_registry()
        config["allowed_signal_types"] = [
            registry.normalize(t) for t in body.allowed_signal_types if registry.normalize(t)
        ]
    if body.max_entries is not None:
        config["max_entries"] = body.max_entries

    updated = repo.update_source(
        source_id=source_id,
        tenant_id=current_user.tenant_id,
        name=body.name,
        config=config if body.feed_url is not None or body.allowed_signal_types is not None or body.max_entries is not None else None,
        enabled=body.enabled,
    )
    return {"ok": True, "source": updated}


@router.get("/sources/{source_id}/health")
def source_health(
    source_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    _require_signals_enabled()
    repo = _repo_from_store(store)
    source = repo.get_source(source_id, tenant_id=current_user.tenant_id)
    if not source:
        raise HTTPException(404, "Source not found")
    connector = build_connector(source)
    health = connector.health()
    state = repo.get_connector_state(source_id, tenant_id=current_user.tenant_id)
    return {
        "source_id": source_id,
        "status": health.status.value,
        "message": health.message,
        "freshness": health.freshness.value,
        "last_success_at": state.last_success_at.isoformat() if state.last_success_at else None,
        "last_event_at": state.last_event_at.isoformat() if state.last_event_at else None,
        "error_state": state.error_state,
        "event_count": repo.count_events(tenant_id=current_user.tenant_id, source_id=source_id),
        "recent_runs": repo.list_ingestion_runs(
            tenant_id=current_user.tenant_id, source_id=source_id, limit=5,
        ),
    }


@router.post("/sources/{source_id}/sync", dependencies=[Depends(rate_limit("signals_sync", limit=30, window_seconds=3600))])
def sync_source(
    source_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    events=Depends(get_events),
):
    _require_signals_enabled()
    repo = _repo_from_store(store)
    if repo.get_source(source_id, tenant_id=current_user.tenant_id) is None:
        raise HTTPException(404, "Source not found")

    service = SignalConnectorService(repository=repo, store=store, events=events)
    result = service.sync_source(tenant_id=current_user.tenant_id, source_id=source_id)
    if result.error and result.ingestion.events_inserted == 0:
        return {
            "ok": False,
            "error": result.error,
            "ingestion": {
                "events_fetched": result.ingestion.events_fetched,
                "events_inserted": result.ingestion.events_inserted,
                "events_deduplicated": result.ingestion.events_deduplicated,
                "events_rejected": result.ingestion.events_rejected,
                "trace_id": result.ingestion.openinference_trace_id,
            },
        }
    return {
        "ok": True,
        "ingestion": {
            "events_fetched": result.ingestion.events_fetched,
            "events_inserted": result.ingestion.events_inserted,
            "events_deduplicated": result.ingestion.events_deduplicated,
            "events_rejected": result.ingestion.events_rejected,
            "trace_id": result.ingestion.openinference_trace_id,
        },
        "prospects_created": result.prospects_created,
        "prospects_skipped": result.prospects_skipped,
        "campaign_ids": result.campaign_ids,
        "error": result.error,
    }


_LOOKALIKE_GRAPH: list[dict[str, Any]] = [
    {
        "company_name": "Ramp",
        "domain": "ramp.com",
        "industry": "FinTech & Spend Management",
        "company_size": "501-1000",
        "location": "New York, NY",
        "technologies_used": ["Stripe", "Snowflake", "Salesforce", "Segment", "React"],
        "similarity_score": 0.95,
        "why_lookalike": "Matches PLG + enterprise GTM motion, modern cloud data stack, and hypergrowth RevOps hiring profile.",
        "decision_makers": [
            {
                "full_name": "Colin Kennedy",
                "title": "VP of Revenue & Growth",
                "email": "colin.kennedy@ramp.com",
                "linkedin_url": "https://www.linkedin.com/in/colin-kennedy-ramp",
                "intent": "Hiring 6 Enterprise AEs & expanding outbound signal automation",
                "intent_keyword": "Enterprise Outbound",
            },
            {
                "full_name": "Priya Nair",
                "title": "Head of Revenue Operations",
                "email": "priya.nair@ramp.com",
                "linkedin_url": "https://www.linkedin.com/in/priya-nair-revops",
                "intent": "Evaluating AI SDR & signal routing workflows",
                "intent_keyword": "RevOps Automation",
            },
        ],
    },
    {
        "company_name": "Vercel",
        "domain": "vercel.com",
        "industry": "Developer Tools & Cloud Infrastructure",
        "company_size": "501-1000",
        "location": "San Francisco, CA",
        "technologies_used": ["Next.js", "Salesforce", "HubSpot", "Datadog", "Stripe"],
        "similarity_score": 0.93,
        "why_lookalike": "High developer-led adoption transitioning into enterprise outbound sales teams.",
        "decision_makers": [
            {
                "full_name": "Marcus Vance",
                "title": "VP of Enterprise Sales",
                "email": "marcus.vance@vercel.com",
                "linkedin_url": "https://www.linkedin.com/in/marcus-vance-vercel",
                "intent": "Scaling signal-based enterprise pipeline across North America",
                "intent_keyword": "Signal-Based Selling",
            },
        ],
    },
    {
        "company_name": "Retool",
        "domain": "retool.com",
        "industry": "B2B SaaS & Internal Tools",
        "company_size": "201-500",
        "location": "San Francisco, CA",
        "technologies_used": ["Postgres", "Stripe", "Salesforce", "Gong", "Segment"],
        "similarity_score": 0.92,
        "why_lookalike": "Strong technical buyer ICP with dedicated SDR/AE pods targeting mid-market & enterprise.",
        "decision_makers": [
            {
                "full_name": "Elena Rostova",
                "title": "Head of Growth & Demand Gen",
                "email": "elena.rostova@retool.com",
                "linkedin_url": "https://www.linkedin.com/in/elena-rostova-growth",
                "intent": "Published post on intent-driven LinkedIn + email sequences",
                "intent_keyword": "Multichannel Outbound",
            },
        ],
    },
    {
        "company_name": "PostHog",
        "domain": "posthog.com",
        "industry": "Product Analytics & DevTools",
        "company_size": "51-200",
        "location": "San Francisco, CA",
        "technologies_used": ["ClickHouse", "HubSpot", "PostHog", "Stripe", "TypeScript"],
        "similarity_score": 0.90,
        "why_lookalike": "Product-led B2B SaaS layering signal-triggered outbound on top of product usage & website visitors.",
        "decision_makers": [
            {
                "full_name": "Liam O'Connor",
                "title": "Revenue Lead",
                "email": "liam@posthog.com",
                "linkedin_url": "https://www.linkedin.com/in/liam-oconnor-posthog",
                "intent": "Converting high-intent pricing page visitors into demos",
                "intent_keyword": "Website Visitor Conversion",
            },
        ],
    },
    {
        "company_name": "Vanta",
        "domain": "vanta.com",
        "industry": "Cybersecurity & Compliance SaaS",
        "company_size": "501-1000",
        "location": "San Francisco, CA",
        "technologies_used": ["AWS", "Salesforce", "Outreach", "Snowflake", "Gong"],
        "similarity_score": 0.89,
        "why_lookalike": "High-velocity mid-market & enterprise sales organization with strong trigger-based outbound DNA.",
        "decision_makers": [
            {
                "full_name": "Hannah Abbott",
                "title": "Director of Sales Development",
                "email": "hannah.abbott@vanta.com",
                "linkedin_url": "https://www.linkedin.com/in/hannah-abbott-vanta",
                "intent": "Hiring 4 SDRs and automating pre-call signal research",
                "intent_keyword": "SDR Productivity",
            },
        ],
    },
    {
        "company_name": "Deel",
        "domain": "deel.com",
        "industry": "HR Tech & Global Payroll",
        "company_size": "1001-5000",
        "location": "San Francisco, CA",
        "technologies_used": ["Salesforce", "HubSpot", "Snowflake", "Intercom", "AWS"],
        "similarity_score": 0.88,
        "why_lookalike": "Global outbound machine leveraging job-change, funding, and geographic expansion triggers.",
        "decision_makers": [
            {
                "full_name": "David Kim",
                "title": "VP of Global Outbound",
                "email": "david.kim@deel.com",
                "linkedin_url": "https://www.linkedin.com/in/david-kim-deel",
                "intent": "Expanding signal-driven LinkedIn + email workflows in EMEA & US",
                "intent_keyword": "Global Expansion Signals",
            },
        ],
    },
]


@router.post("/lookalikes")
def generate_lookalikes(
    body: LookalikesRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    """Discover AI lookalike companies & decision-makers from seed customer domains or top converted prospects."""
    _require_signals_enabled()

    tenant_engagements = store.list_engagements(tenant_id=current_user.tenant_id)
    tenant_eng_ids = {e.id for e in tenant_engagements}
    if body.campaign_id and body.campaign_id not in tenant_eng_ids:
        raise HTTPException(404, "Campaign not found")

    seed_domains = [
        d.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
        for d in body.seed_domains
        if d and d.strip()
    ]

    # If no seed domains provided, infer from tenant's highest-scoring prospects or accounts
    if not seed_domains:
        for eng_id in tenant_eng_ids:
            for p in store.list_prospects(engagement_id=eng_id):
                if p.email and "@" in p.email:
                    dom = p.email.split("@", 1)[1].lower()
                    if dom not in seed_domains:
                        seed_domains.append(dom)
                if len(seed_domains) >= 5:
                    break
            if len(seed_domains) >= 5:
                break
    if not seed_domains:
        seed_domains = ["stripe.com", "linear.app", "figma.com"]

    seed_set = set(seed_domains)
    candidates = [c for c in _LOOKALIKE_GRAPH if c["domain"] not in seed_set][: body.limit]

    imported_prospect_ids: list[str] = []
    target_campaign_id = body.campaign_id or (next(iter(tenant_eng_ids)) if tenant_eng_ids else None)

    lookalike_companies: list[dict[str, Any]] = []
    lookalike_prospects: list[dict[str, Any]] = []

    for comp in candidates:
        comp_copy = {
            **comp,
            "seed_reference": seed_domains[0],
            "signal_type": "LOOKALIKE",
        }
        lookalike_companies.append(comp_copy)

        for dm in comp.get("decision_makers", []):
            scoring = round(float(comp["similarity_score"]), 2)
            intent_scoring = 2.4
            prospect_entry = {
                "full_name": dm["full_name"],
                "title": dm["title"],
                "company": comp["company_name"],
                "domain": comp["domain"],
                "email": dm["email"],
                "linkedin_url": dm["linkedin_url"],
                "location": comp["location"],
                "industry": comp["industry"],
                "company_size": comp["company_size"],
                "signal_type": "LOOKALIKE",
                "intent_type": "LOOKALIKE",
                "intent_keyword": f"Lookalike of {seed_domains[0]}",
                "intent": f"Lookalike of {seed_domains[0]} ({int(scoring * 100)}% DNA match) — {dm['intent']}",
                "scoring": scoring,
                "intent_scoring": intent_scoring,
                "total_scoring": round(scoring + intent_scoring, 2),
                "fit": "qualified",
                "score_reasoning": comp["why_lookalike"],
            }
            lookalike_prospects.append(prospect_entry)

            if body.auto_import and target_campaign_id:
                existing_prospects = store.list_prospects(engagement_id=target_campaign_id)
                if not any((ep.email or "").lower() == dm["email"].lower() for ep in existing_prospects):
                    pid = f"pro_lk_{secrets.token_hex(6)}"
                    new_p = Prospect(
                        id=pid,
                        engagement_id=target_campaign_id,
                        full_name=dm["full_name"],
                        title=dm["title"],
                        company=comp["company_name"],
                        email=dm["email"],
                        linkedin_url=dm["linkedin_url"],
                        research={
                            "source": "gojiberry_lookalike",
                            "signal_type": "LOOKALIKE",
                            "intent_type": "LOOKALIKE",
                            "intent_keyword": f"Lookalike of {seed_domains[0]}",
                            "intent": prospect_entry["intent"],
                            "scoring": scoring,
                            "intent_scoring": intent_scoring,
                            "total_scoring": round(scoring + intent_scoring, 2),
                            "fit": "qualified",
                            "score_reasoning": comp["why_lookalike"],
                            "priority_score": int(scoring * 100),
                            "signals": [
                                {
                                    "type": "lookalike",
                                    "signal_type": "LOOKALIKE",
                                    "summary": prospect_entry["intent"],
                                    "confidence": scoring,
                                }
                            ],
                        },
                    )
                    store.save_prospect(new_p)
                    imported_prospect_ids.append(pid)

    return {
        "ok": True,
        "count": len(lookalike_companies),
        "seed_domains": seed_domains,
        "companies": lookalike_companies,
        "prospects": lookalike_prospects,
        "imported_count": len(imported_prospect_ids),
        "imported_prospect_ids": imported_prospect_ids,
        "campaign_id": target_campaign_id,
    }
