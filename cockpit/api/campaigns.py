"""
REST API: Campaigns (≡ Engagements)

GET    /api/campaigns
POST   /api/campaigns
GET    /api/campaigns/{id}
PATCH  /api/campaigns/{id}
DELETE /api/campaigns/{id}
POST   /api/campaigns/{id}/tick
POST   /api/campaigns/{id}/drain
POST   /api/campaigns/{id}/poll-replies
POST   /api/campaigns/{id}/approve-job/{job_id}
POST   /api/campaigns/{id}/reject-job/{job_id}
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from cockpit.api.deps import (
    get_current_user, get_events, get_ledger, get_ops,
    get_pnl, get_reply_detector, get_runtime, get_store,
)
from engine.auth import CurrentUser

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class CampaignCreate(BaseModel):
    customer_name: str
    offer: str
    icp_description: str
    client_cure: Optional[str] = None
    allowed_signal_types: list[str] = []
    min_signal_stack: int = 1
    booking_url: Optional[str] = None
    monthly_meeting_target: Optional[int] = None
    price_per_outcome_cents: Optional[int] = None
    monthly_budget_cents: Optional[int] = None
    hitl_threshold: int = 50
    send_gap_seconds: int = 60
    personalize_enabled: bool = False
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    sequence: Optional[list[dict[str, Any]]] = None
    reply_mode: Optional[str] = "hitl"
    message_mode: Optional[str] = "ai"
    tone: Optional[str] = "conversational"
    goal: Optional[str] = "book_meeting"
    agent_type: Optional[str] = "autopilot"
    min_lead_score: Optional[float] = 0.6
    skip_invitation_after_days: Optional[int] = 7
    split_linkedin_messages: Optional[bool] = False
    signal_variables: Optional[list[dict[str, Any]]] = None
    target_job_titles: Optional[list[str]] = None
    target_industries: Optional[list[str]] = None
    target_company_sizes: Optional[list[str]] = None
    target_locations: Optional[list[str]] = None
    target_company_types: Optional[list[str]] = None
    search_keywords: Optional[list[str]] = None
    source_website: Optional[str] = None
    auto_discover_people: bool = True
    discovery_cap: Optional[int] = None


class CampaignPatch(BaseModel):
    customer_name: Optional[str] = None
    offer: Optional[str] = None
    icp_description: Optional[str] = None
    client_cure: Optional[str] = None
    allowed_signal_types: Optional[list[str]] = None
    min_signal_stack: Optional[int] = None
    booking_url: Optional[str] = None
    status: Optional[str] = None
    monthly_meeting_target: Optional[int] = None
    price_per_outcome_cents: Optional[int] = None
    monthly_budget_cents: Optional[int] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    sequence: Optional[list[dict[str, Any]]] = None
    reply_mode: Optional[str] = None
    message_mode: Optional[str] = None
    tone: Optional[str] = None
    goal: Optional[str] = None
    agent_type: Optional[str] = None
    min_lead_score: Optional[float] = None
    skip_invitation_after_days: Optional[int] = None
    split_linkedin_messages: Optional[bool] = None
    signal_variables: Optional[list[dict[str, Any]]] = None
    target_job_titles: Optional[list[str]] = None
    target_industries: Optional[list[str]] = None
    target_company_sizes: Optional[list[str]] = None
    target_locations: Optional[list[str]] = None
    target_company_types: Optional[list[str]] = None
    search_keywords: Optional[list[str]] = None
    source_website: Optional[str] = None


class DiscoverPeopleRequest(BaseModel):
    job_titles: Optional[list[str]] = None
    search_keywords: Optional[list[str]] = None
    industries: Optional[list[str]] = None
    locations: Optional[list[str]] = None
    cap: Optional[int] = None


class SimulatedSignal(BaseModel):
    signal_type: str
    company_domain: str
    payload: dict = {}


class SimulateSignalsRequest(BaseModel):
    signals: list[SimulatedSignal]


class LeadScrapeRequest(BaseModel):
    source_url: str


def _job_action_dict(job, store) -> dict[str, Any]:
    """US-003: enrich a pending job for the Actions/reasoning UI — draft, guardian
    risk, the prospect's signal-stack evidence, trace id, and HITL reason."""
    payload = dict(job.payload or {})
    prospect = store.get_prospect(job.prospect_id) if job.prospect_id else None
    research = prospect.research if prospect and isinstance(prospect.research, dict) else {}
    matched = research.get("matched_intent_signal") if isinstance(research, dict) else None
    trace_id = matched.get("openinference_trace_id") if isinstance(matched, dict) else None
    risk = payload.get("deliverability_risk")
    hitl_reason = None
    if isinstance(risk, dict) and risk.get("level") == "block":
        hitl_reason = "Deliverability Guardian flagged this draft as high-risk — human approval required."
    scoring = research.get("scoring") if isinstance(research, dict) else None
    intent_scoring = research.get("intent_scoring") if isinstance(research, dict) else None
    total_scoring = research.get("total_scoring") if isinstance(research, dict) else None
    from engine.adapters.email_merge import merge_email_copy

    rendered_subject, rendered_body, _html = merge_email_copy(payload)
    return {
        "id": job.id,
        "kind": job.kind.value,
        "to_email": payload.get("to_email") or payload.get("to"),
        "company": payload.get("company") or (prospect.company if prospect else None),
        "subject": rendered_subject or payload.get("subject") or payload.get("subject_template", "")[:80],
        "body_text": rendered_body or payload.get("body_text", ""),
        "copy_quality_error": payload.get("copy_quality_error") or getattr(job, "last_error", None),
        "prospect_id": job.prospect_id,
        "deliverability_risk": risk,
        "signal_stack": research.get("signal_stack") if isinstance(research, dict) else None,
        "openinference_trace_id": trace_id,
        "hitl_reason": hitl_reason,
        "snoozed_until": payload.get("snoozed_until"),
        "edited": payload.get("edited", False),
        "channel": payload.get("channel") or "email",
        "step_type": payload.get("step_type"),
        "scoring": scoring,
        "intent_scoring": intent_scoring,
        "total_scoring": total_scoring,
        "score_gate": False,
        "state": job.state,
    }


def _channels_from_sequence(sequence: list | None) -> list[str]:
    """Derive display channels from saved sequence steps (Email / LinkedIn)."""
    from engine.agents.outbound_agent import step_is_linkedin

    channels: list[str] = []
    seen: set[str] = set()
    seq = sequence if isinstance(sequence, list) else []
    if not seq:
        return ["Email"]
    for step in seq:
        if not isinstance(step, dict):
            continue
        label = "LinkedIn" if step_is_linkedin(step) else "Email"
        if label not in seen:
            seen.add(label)
            channels.append(label)
    return channels or ["Email"]


def _execution_mode_label(metadata: dict) -> str:
    reply = str(metadata.get("reply_mode") or "hitl").strip().lower()
    if reply in {"auto", "full_auto", "autonomous"}:
        return "Full Auto"
    return "AI Copilot"


def _eng_to_dict(eng, report=None):
    metadata = dict(getattr(eng, "metadata", {}) or {})
    signal_matrix = dict(metadata.get("signal_matrix") or {})
    sequence = metadata.get("sequence", [])
    d = {
        "id": eng.id, "customer_name": eng.customer_name,
        "offer": eng.offer, "icp_description": eng.icp_description,
        "client_cure": metadata.get("client_cure", ""),
        "signal_matrix": signal_matrix,
        "allowed_signal_types": signal_matrix.get("allowed_signal_types", []),
        "min_signal_stack": signal_matrix.get("min_signal_stack", 1),
        "deliverability_preflight": metadata.get("deliverability_preflight", {}),
        "subject_template": metadata.get("subject_template"),
        "body_template": metadata.get("body_template"),
        "sequence": sequence,
        "channels": _channels_from_sequence(sequence),
        "execution_mode": _execution_mode_label(metadata),
        "reply_mode": metadata.get("reply_mode", "hitl"),
        "message_mode": metadata.get("message_mode", "ai"),
        "tone": metadata.get("tone", "conversational"),
        "goal": metadata.get("goal", "book_meeting"),
        "agent_type": metadata.get("agent_type", "autopilot"),
        "min_lead_score": metadata.get("min_lead_score", 0.6),
        "skip_invitation_after_days": metadata.get("skip_invitation_after_days", 7),
        "split_linkedin_messages": metadata.get("split_linkedin_messages", False),
        "signal_variables": metadata.get("signal_variables", []),
        "target_job_titles": metadata.get("target_job_titles", []),
        "target_industries": metadata.get("target_industries", []),
        "target_company_sizes": metadata.get("target_company_sizes", []),
        "target_locations": metadata.get("target_locations", []),
        "target_company_types": metadata.get("target_company_types", []),
        "search_keywords": metadata.get("search_keywords", []),
        "source_website": metadata.get("source_website"),
        "people_discovery": metadata.get("people_discovery") or {},
        "booking_url": eng.booking_url, "status": eng.status,
        "monthly_meeting_target": eng.monthly_meeting_target,
        "price_per_outcome_cents": eng.price_per_outcome_cents,
        "monthly_budget_cents": eng.monthly_budget_cents,
        "created_at": eng.created_at.isoformat() if eng.created_at else None,
    }
    if report:
        d["pnl"] = {
            "revenue_cents": report.revenue_cents,
            "cost_cents": report.cost_cents,
            "margin_cents": report.margin_cents,
            "margin_pct": report.margin_pct,
            "cost_by_category_cents": report.cost_by_category_cents,
            "cost_per_qualified_outcome_cents": report.cost_per_qualified_outcome_cents,
            "profit_per_qualified_outcome_cents": report.profit_per_qualified_outcome_cents,
            "budget_remaining_cents": report.budget_remaining_cents,
            "budget_spent_pct": report.budget_spent_pct,
            "over_budget": report.over_budget,
            "booked_count": report.booked_count,
            "qualified_count": report.qualified_count,
        }
    return d


@router.get("")
def list_campaigns(
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    pnl=Depends(get_pnl),
):
    engagements = [
        e for e in store.list_engagements(tenant_id=current_user.tenant_id)
        if e.status != "cancelled"
    ]
    return [_eng_to_dict(e, pnl.report_for(e.id)) for e in engagements]


@router.post("", status_code=201)
def create_campaign(
    body: CampaignCreate,
    current_user: CurrentUser = Depends(get_current_user),
    ops=Depends(get_ops),
    store=Depends(get_store),
):
    # M5: enforce plan campaign cap.
    from engine.policies import get_plan_limits
    limits = get_plan_limits(current_user.plan)
    existing = [e for e in store.list_engagements(tenant_id=current_user.tenant_id)
                if e.status != "cancelled"]
    if len(existing) >= limits.max_campaigns:
        raise HTTPException(
            403,
            f"Plan '{limits.plan}' allows {limits.max_campaigns} campaign(s). Upgrade to add more.",
        )
    # M5: personalization gated by plan.
    personalize = body.personalize_enabled and limits.personalization

    eng = ops.create_engagement(
        customer_name=body.customer_name,
        offer=body.offer,
        icp_description=body.icp_description,
        booking_url=body.booking_url,
        monthly_meeting_target=body.monthly_meeting_target,
        price_per_outcome_cents=body.price_per_outcome_cents,
        monthly_budget_cents=body.monthly_budget_cents,
    )
    eng = replace(eng, metadata=_campaign_metadata(body))
    store.save_engagement(eng, tenant_id=current_user.tenant_id)

    ops.create_agent(
        engagement_id=eng.id,
        runner_kind="outbound.v1",
        config={
            "hitl_threshold": body.hitl_threshold,
            "send_gap_seconds": body.send_gap_seconds,
            "personalize": personalize,
            **({
                "subject_template": body.subject_template.strip(),
            } if body.subject_template and body.subject_template.strip() else {}),
            **({
                "body_template": body.body_template.strip(),
            } if body.body_template and body.body_template.strip() else {}),
            **({"sequence": _normalize_sequence(body.sequence)} if body.sequence else {}),
            "reply_mode": body.reply_mode or "hitl",
            "message_mode": body.message_mode or "ai",
            "tone": body.tone or "conversational",
            "goal": body.goal or "book_meeting",
            "agent_type": body.agent_type or "autopilot",
            "min_lead_score": body.min_lead_score if body.min_lead_score is not None else 0.6,
            "skip_invitation_after_days": body.skip_invitation_after_days if body.skip_invitation_after_days is not None else 7,
            "split_linkedin_messages": bool(body.split_linkedin_messages),
            **({"signal_variables": body.signal_variables} if body.signal_variables else {}),
        },
    )
    created = _eng_to_dict(eng)
    if body.auto_discover_people:
        from engine.services.people_discovery import kickoff_campaign_people_discovery

        discovery = kickoff_campaign_people_discovery(
            store,
            tenant_id=current_user.tenant_id,
            campaign_id=eng.id,
            cap=body.discovery_cap,
        )
        created["people_discovery"] = discovery.get("people_discovery") or {
            "status": discovery.get("status"),
            "message": discovery.get("message"),
            "cap": discovery.get("cap"),
            "found": discovery.get("created", 0),
        }
        created["discovery_kickoff"] = {
            "status": discovery.get("status"),
            "message": discovery.get("message"),
            "created": discovery.get("created", 0),
        }
    return created


@router.get("/prompt-templates")
def get_campaign_prompt_templates(
    channel: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    from engine.llm.prompt_templates import get_gojiberry_prompt_templates
    templates = get_gojiberry_prompt_templates(channel=channel)
    return {"count": len(templates), "templates": templates}


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    pnl=Depends(get_pnl),
    events=Depends(get_events),
):
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    report = pnl.report_for(campaign_id)
    recent_events = [
        {"kind": e.kind.value, "occurred_at": e.occurred_at.isoformat(),
         "job_id": e.job_id, "prospect_id": e.prospect_id, "payload": dict(e.payload)}
        for e in events.list_recent(engagement_id=campaign_id, limit=25)
    ]
    jobs_awaiting = [
        _job_action_dict(j, store)
        for j in store.list_jobs_by_state("awaiting_approval", engagement_id=campaign_id)
    ]
    return {
        **_eng_to_dict(eng, report),
        "agents": [{"id": a.id, "runner_kind": a.runner_kind, "status": a.status, "config": dict(a.config)}
                   for a in store.list_agents(campaign_id)],
        "prospect_count": len(list(store.list_prospects(campaign_id, limit=10_000))),
        "pending_replies": len(list(store.list_replies(campaign_id, status="pending"))),
        "events": recent_events,
        "jobs_awaiting_approval": jobs_awaiting,
    }


@router.get("/{campaign_id}/accounts")
def list_campaign_accounts(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    accounts = store.list_accounts(campaign_id, tenant_id=current_user.tenant_id)
    prospects = list(store.list_prospects(campaign_id, limit=100_000))
    by_account: dict[str, list] = {}
    for p in prospects:
        research = p.research if isinstance(p.research, dict) else {}
        aid = research.get("account_id")
        if aid:
            by_account.setdefault(aid, []).append(p)
    out = []
    for acct in accounts:
        contacts = by_account.get(acct.id, [])
        with_email = sum(1 for p in contacts if str(p.email or "").strip())
        out.append({
            "id": acct.id,
            "company_domain": acct.company_domain,
            "company_name": acct.company_name,
            "contact_count": len(contacts),
            "contactable_count": with_email,
            "evidence": list(acct.evidence or [])[:10],
            "updated_at": acct.updated_at.isoformat() if acct.updated_at else None,
        })
    return {"data": out, "total": len(out)}


@router.post("/{campaign_id}/signals/simulate")
def simulate_signals(
    campaign_id: str,
    body: SimulateSignalsRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    events=Depends(get_events),
):
    """Ingest signals for a campaign and create stacked prospects.

    Development/test tool — source is MANUAL, not external live ingestion.
    Persists through SignalIngestionService then IntentProspectIngestor.
    """
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    if not body.signals:
        raise HTTPException(400, "No signals provided")

    from engine.intent.ingestor import IntentProspectIngestor
    from engine.signals.bridge import StoreIntentRepository
    from engine.signals.connectors.manual import ManualSignalConnector
    from engine.signals.ingestion import SignalIngestionService
    from engine.signals.repository import SignalRepository

    repo = SignalRepository(store._holder.engine)
    source_id = f"manual_sim_{campaign_id[:12]}"
    repo.save_source(
        source_id=source_id,
        tenant_id=current_user.tenant_id,
        connector_kind="manual",
        name=f"Simulate ({campaign_id})",
        config={"dev_tool": True},
    )
    connector = ManualSignalConnector(source_id=source_id)
    payloads = [
        {
            "signal_type": s.signal_type,
            "company_domain": s.company_domain,
            "company_name": (s.payload or {}).get("company"),
            "payload": dict(s.payload or {}),
            "evidence": {"summary": (s.payload or {}).get("summary", f"{s.signal_type} at {s.company_domain}")},
        }
        for s in body.signals
    ]
    ingestion = SignalIngestionService(repository=repo).ingest_manual_payloads(
        tenant_id=current_user.tenant_id,
        source_id=source_id,
        connector=connector,
        payloads=payloads,
    )

    bridge_repo = StoreIntentRepository(repository=repo)
    result = IntentProspectIngestor(store=store, events=events, repository=bridge_repo).ingest_campaign(
        tenant_id=current_user.tenant_id, engagement_id=campaign_id,
    )

    prospects = []
    for pid in result.created_prospect_ids:
        p = store.get_prospect(pid)
        if p is None:
            continue
        research = p.research if isinstance(p.research, dict) else {}
        prospects.append({
            "id": p.id,
            "company": p.company,
            "email": p.email,
            "signal_stack": research.get("signal_stack"),
        })

    metadata = dict(getattr(eng, "metadata", {}) or {})
    return {
        "created_count": result.created_count,
        "skipped_count": result.skipped_count,
        "min_signal_stack": (metadata.get("signal_matrix") or {}).get("min_signal_stack", 1),
        "prospects": prospects,
        "openinference_trace_id": result.openinference_trace_id,
        "source": "manual",
        "events_persisted": ingestion.events_inserted,
        "events_deduplicated": ingestion.events_deduplicated,
        "events_rejected": ingestion.events_rejected,
    }


@router.post("/{campaign_id}/leads/scrape")
def scrape_leads(
    campaign_id: str,
    body: LeadScrapeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    """Scrape a named source (Firecrawl) → LLM extracts ICP leads → prospects.

    Leads without an email are created but NOT contactable (the outbound agent
    skips no-email prospects) — surfaced honestly, never faked as send-ready.
    Human approval still gates every send.
    """
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    source_url = body.source_url.strip()
    if not source_url:
        raise HTTPException(400, "source_url is required")

    import hashlib
    from engine.core.types import Prospect
    from engine.services.lead_scraper import scrape_leads_from_source

    leads = scrape_leads_from_source(source_url, icp=eng.icp_description or "")
    from engine.policies import assert_under_lead_cap

    # Cap check against net-new prospects only (existing IDs are skipped below).
    new_candidates = 0
    for lead in leads:
        seed = "|".join([current_user.tenant_id, campaign_id, lead.company_domain or lead.email or lead.company])
        pid = f"p_scrape_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:20]}"
        if store.get_prospect(pid) is None:
            new_candidates += 1
    if new_candidates:
        assert_under_lead_cap(
            store,
            tenant_id=current_user.tenant_id,
            plan=current_user.plan,
            delta=new_candidates,
        )
    created = 0
    with_email = 0
    out = []
    for lead in leads:
        seed = "|".join([current_user.tenant_id, campaign_id, lead.company_domain or lead.email or lead.company])
        pid = f"p_scrape_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:20]}"
        if store.get_prospect(pid) is not None:
            continue
        email = lead.email or None
        from engine.services.accounts import upsert_account

        account = upsert_account(
            store,
            tenant_id=current_user.tenant_id,
            engagement_id=campaign_id,
            company_domain=lead.company_domain or lead.company or "",
            company_name=lead.company or lead.company_domain,
        )
        research = {"source": "firecrawl_scrape", "source_url": source_url}
        if account:
            research["account_id"] = account.id
            research["company_domain"] = account.company_domain
        store.save_prospect(
            Prospect(
                id=pid,
                engagement_id=campaign_id,
                email=email,
                full_name=lead.full_name or None,
                company=lead.company or lead.company_domain,
                title=lead.title or None,
                raw={"scraped_lead": {"company_domain": lead.company_domain, "source_url": source_url}},
                research=research,
                status="new",
            ),
            tenant_id=current_user.tenant_id,
        )
        created += 1
        with_email += 1 if email else 0
        out.append({"id": pid, "company": lead.company or lead.company_domain, "email": email, "contactable": bool(email)})

    return {
        "scraped_count": len(leads),
        "created_count": created,
        "with_email": with_email,
        "without_email": created - with_email,
        "note": "Leads without an email are created but not contactable until an email is verified/added.",
        "prospects": out,
    }


@router.post("/{campaign_id}/discover-people")
def discover_campaign_people(
    campaign_id: str,
    body: DiscoverPeopleRequest = Body(default_factory=DiscoverPeopleRequest),
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    """Re-run SourceAgent-style people search from this campaign's ICP.

    Uses stored job titles + keywords + industries + locations. Optional body
    fields overwrite those ICP lists before searching. CSV is not required.
    """
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    metadata = dict(eng.metadata or {})
    if body.job_titles is not None:
        metadata["target_job_titles"] = body.job_titles
    if body.search_keywords is not None:
        metadata["search_keywords"] = body.search_keywords
    if body.industries is not None:
        metadata["target_industries"] = body.industries
    if body.locations is not None:
        metadata["target_locations"] = body.locations
    if body.cap is not None:
        metadata["discovery_cap"] = body.cap
    if metadata != dict(eng.metadata or {}):
        eng = replace(eng, metadata=metadata)
        store.save_engagement(eng, tenant_id=current_user.tenant_id)

    from engine.services.people_discovery import kickoff_campaign_people_discovery

    result = kickoff_campaign_people_discovery(
        store,
        tenant_id=current_user.tenant_id,
        campaign_id=campaign_id,
        cap=body.cap,
    )
    latest = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    payload = _eng_to_dict(latest) if latest else {}
    payload.update({
        "ok": bool(result.get("ok", True)),
        "discovery": result,
        "created_count": result.get("created", 0),
        "with_email": result.get("with_email", 0),
        "prospects": result.get("prospects") or [],
    })
    from engine.debug_agent import agent_debug
    agent_debug(
        "E",
        "campaigns.py:discover_campaign_people",
        "discover result",
        {
            "campaign_id": campaign_id,
            "ok": payload["ok"],
            "created_count": payload["created_count"],
            "with_email": payload["with_email"],
            "queued": bool((result.get("people_discovery") or {}).get("queued")),
            "status": (result.get("people_discovery") or {}).get("status"),
            "message": str((result.get("people_discovery") or {}).get("message") or "")[:160],
        },
    )
    return payload


@router.patch("/{campaign_id}")
def patch_campaign(
    campaign_id: str,
    body: CampaignPatch,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    if body.status is not None and body.status not in _ALLOWED_CAMPAIGN_STATUSES:
        raise HTTPException(
            400,
            f"Invalid status '{body.status}'. Allowed: {sorted(_ALLOWED_CAMPAIGN_STATUSES)}",
        )
    from engine.core.types import Engagement as _Eng
    metadata = _patched_campaign_metadata(eng.metadata, body)
    updated = _Eng(
        id=eng.id,
        customer_name=body.customer_name or eng.customer_name,
        offer=body.offer or eng.offer,
        icp_description=body.icp_description or eng.icp_description,
        icp_filters=eng.icp_filters,
        booking_url=body.booking_url if body.booking_url is not None else eng.booking_url,
        monthly_meeting_target=body.monthly_meeting_target if body.monthly_meeting_target is not None else eng.monthly_meeting_target,
        price_per_outcome_cents=body.price_per_outcome_cents if body.price_per_outcome_cents is not None else eng.price_per_outcome_cents,
        monthly_budget_cents=body.monthly_budget_cents if body.monthly_budget_cents is not None else eng.monthly_budget_cents,
        status=body.status or eng.status,
        created_at=eng.created_at,
        metadata=metadata,
    )
    store.save_engagement(updated, tenant_id=current_user.tenant_id)
    # Sync updated settings into the campaign's Agent config
    for agent in store.list_agents(campaign_id):
        cfg = dict(agent.config or {})
        for field_name in (
            "subject_template",
            "body_template",
            "sequence",
            "reply_mode",
            "message_mode",
            "tone",
            "goal",
            "agent_type",
            "min_lead_score",
            "skip_invitation_after_days",
            "split_linkedin_messages",
            "signal_variables",
            "target_job_titles",
            "target_industries",
            "target_company_sizes",
            "target_locations",
            "target_company_types",
            "search_keywords",
        ):
            val = getattr(body, field_name, None)
            if val is not None:
                cfg[field_name] = val
        store.save_agent(replace(agent, config=cfg))
    return _eng_to_dict(updated)


@router.patch("/{campaign_id}/settings")
def patch_campaign_settings(
    campaign_id: str,
    body: CampaignPatch,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    ops=Depends(get_ops),
):
    """Update Gojiberry Full-Cycle Agent settings (reply_mode, message_mode, tone, goal, min_lead_score, sequence, signal_variables)."""
    return patch_campaign(
        campaign_id=campaign_id,
        body=body,
        current_user=current_user,
        store=store,
        ops=ops,
    )


_ALLOWED_CAMPAIGN_STATUSES = frozenset({"active", "paused", "cancelled"})


@router.post("/{campaign_id}/pause")
def pause_campaign(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    """Pilot kill switch — stops planning/sends for this campaign (status=paused)."""
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    from engine.core.types import Engagement as _Eng
    updated = _Eng(
        id=eng.id, customer_name=eng.customer_name, offer=eng.offer,
        icp_description=eng.icp_description, icp_filters=eng.icp_filters,
        booking_url=eng.booking_url,
        monthly_meeting_target=eng.monthly_meeting_target,
        price_per_outcome_cents=eng.price_per_outcome_cents,
        monthly_budget_cents=eng.monthly_budget_cents,
        status="paused", created_at=eng.created_at, metadata=eng.metadata,
    )
    store.save_engagement(updated, tenant_id=current_user.tenant_id)
    return {"ok": True, "id": campaign_id, "status": "paused"}


@router.post("/{campaign_id}/resume")
def resume_campaign(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    """Resume a paused campaign (status=active)."""
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    if eng.status == "cancelled":
        raise HTTPException(400, "Cannot resume a cancelled campaign")
    from engine.core.types import Engagement as _Eng
    updated = _Eng(
        id=eng.id, customer_name=eng.customer_name, offer=eng.offer,
        icp_description=eng.icp_description, icp_filters=eng.icp_filters,
        booking_url=eng.booking_url,
        monthly_meeting_target=eng.monthly_meeting_target,
        price_per_outcome_cents=eng.price_per_outcome_cents,
        monthly_budget_cents=eng.monthly_budget_cents,
        status="active", created_at=eng.created_at, metadata=eng.metadata,
    )
    store.save_engagement(updated, tenant_id=current_user.tenant_id)
    return {"ok": True, "id": campaign_id, "status": "active"}


def _normalize_sequence(values: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Accept wizard `{kind, delay}` rows and Gojiberry `{type, delay_days}` rows."""
    if not values:
        return []
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(values):
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("type") or raw.get("kind") or raw.get("channel") or "").strip()
        channel = str(raw.get("channel") or "").strip().lower()
        if not channel:
            channel = "email" if kind.lower() == "email" else ("linkedin" if kind else "email")
        wait = raw.get("wait_days")
        if wait is None:
            wait = raw.get("delay_days")
        if wait is None:
            delay_text = str(raw.get("delay") or "")
            digits = "".join(ch for ch in delay_text if ch.isdigit())
            wait = int(digits) if digits else 0
        try:
            wait_days = max(0, int(wait or 0))
        except (TypeError, ValueError):
            wait_days = 0
        step = {
            "step": raw.get("step") or i + 1,
            "type": kind or "email",
            "kind": kind or "email",
            "channel": channel,
            "wait_days": wait_days,
            "delay_days": wait_days,
            "label": raw.get("label") or kind or f"step-{i + 1}",
        }
        if raw.get("subject_template"):
            step["subject_template"] = raw["subject_template"]
        if raw.get("body_template"):
            step["body_template"] = raw["body_template"]
        out.append(step)
    return out


def _normalize_signal_types(values: list[str] | None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        signal_type = str(value).strip()
        if not signal_type or signal_type in seen:
            continue
        seen.add(signal_type)
        normalized.append(signal_type)
    return normalized


def _campaign_metadata(body: CampaignCreate) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    client_cure = (body.client_cure or "").strip()
    if client_cure:
        metadata["client_cure"] = client_cure
    allowed = _normalize_signal_types(body.allowed_signal_types)
    if allowed:
        metadata["signal_matrix"] = {
            "allowed_signal_types": allowed,
            "min_signal_stack": max(1, int(body.min_signal_stack or 1)),
        }
    if body.subject_template and body.subject_template.strip():
        metadata["subject_template"] = body.subject_template.strip()
    if body.body_template and body.body_template.strip():
        metadata["body_template"] = body.body_template.strip()
    if body.sequence is not None:
        metadata["sequence"] = _normalize_sequence(body.sequence)
    if not metadata.get("signal_variables") and body.search_keywords:
        # Python 3.11 (Docker) cannot parse backslashes inside f-string expressions.
        quoted_keywords = []
        for keyword in body.search_keywords:
            cleaned = str(keyword).strip().strip('"')
            if cleaned:
                quoted_keywords.append({"type": "SEARCH_KEYWORD", "value": f'"{cleaned}"'})
        if quoted_keywords:
            metadata["signal_variables"] = quoted_keywords[:10]
    if body.reply_mode:
        metadata["reply_mode"] = body.reply_mode
    if body.message_mode:
        metadata["message_mode"] = body.message_mode
    if body.tone:
        metadata["tone"] = body.tone
    if body.goal:
        metadata["goal"] = body.goal
    if body.agent_type:
        metadata["agent_type"] = body.agent_type
    if body.min_lead_score is not None:
        metadata["min_lead_score"] = body.min_lead_score
    if body.skip_invitation_after_days is not None:
        metadata["skip_invitation_after_days"] = body.skip_invitation_after_days
    if body.split_linkedin_messages is not None:
        metadata["split_linkedin_messages"] = body.split_linkedin_messages
    if body.signal_variables is not None:
        metadata["signal_variables"] = body.signal_variables
    for icp_field in (
        "target_job_titles",
        "target_industries",
        "target_company_sizes",
        "target_locations",
        "target_company_types",
        "search_keywords",
    ):
        val = getattr(body, icp_field, None)
        if val is not None:
            metadata[icp_field] = val
    if body.source_website and body.source_website.strip():
        metadata["source_website"] = body.source_website.strip()
    if body.discovery_cap is not None:
        from engine.services.people_discovery import clamp_discovery_cap

        metadata["discovery_cap"] = clamp_discovery_cap(body.discovery_cap)
    return metadata


def _patched_campaign_metadata(existing: Any, body: CampaignPatch) -> dict[str, Any]:
    metadata = dict(existing or {})
    if body.client_cure is not None:
        client_cure = body.client_cure.strip()
        if client_cure:
            metadata["client_cure"] = client_cure
        else:
            metadata.pop("client_cure", None)
    if body.allowed_signal_types is not None:
        allowed = _normalize_signal_types(body.allowed_signal_types)
        if allowed:
            prior = dict(metadata.get("signal_matrix") or {})
            metadata["signal_matrix"] = {
                "allowed_signal_types": allowed,
                "min_signal_stack": max(1, int(body.min_signal_stack or prior.get("min_signal_stack", 1))),
            }
        else:
            metadata.pop("signal_matrix", None)
    elif body.min_signal_stack is not None and isinstance(metadata.get("signal_matrix"), dict):
        metadata["signal_matrix"]["min_signal_stack"] = max(1, int(body.min_signal_stack))
    for field_name in (
        "subject_template",
        "body_template",
        "sequence",
        "reply_mode",
        "message_mode",
        "tone",
        "goal",
        "agent_type",
        "min_lead_score",
        "skip_invitation_after_days",
        "split_linkedin_messages",
        "signal_variables",
        "target_job_titles",
        "target_industries",
        "target_company_sizes",
        "target_locations",
        "target_company_types",
        "search_keywords",
        "source_website",
    ):
        val = getattr(body, field_name, None)
        if val is not None:
            metadata[field_name] = val
    return metadata


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    from engine.core.types import Engagement as _Eng
    cancelled = _Eng(
        id=eng.id, customer_name=eng.customer_name, offer=eng.offer,
        icp_description=eng.icp_description, icp_filters=eng.icp_filters,
        booking_url=eng.booking_url, monthly_meeting_target=eng.monthly_meeting_target,
        price_per_outcome_cents=eng.price_per_outcome_cents,
        monthly_budget_cents=eng.monthly_budget_cents,
        status="cancelled", created_at=eng.created_at, metadata=eng.metadata,
    )
    store.save_engagement(cancelled, tenant_id=current_user.tenant_id)


@router.post("/{campaign_id}/tick")
def tick_campaign(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    runtime=Depends(get_runtime),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    result = runtime.tick(
        tenant_id=current_user.tenant_id,
        engagement_id=campaign_id,
    )
    return {"ok": True, "result": result}


@router.post("/{campaign_id}/drain")
def drain_campaign(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    runtime=Depends(get_runtime),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    result = runtime.run_once(
        max_iters=20,
        tenant_id=current_user.tenant_id,
        engagement_id=campaign_id,
    )
    return {"ok": True, "result": result}


@router.post("/{campaign_id}/poll-replies")
def poll_replies(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    detector=Depends(get_reply_detector),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    if detector is None:
        raise HTTPException(400, "Gmail reply detector not configured")
    result = detector.poll(campaign_id)
    return {
        "ok": True,
        "prospects_scanned": result.prospects_scanned,
        "replies_recorded": result.replies_recorded,
        "auto_responders": result.auto_responders,
        "token_invalid": result.token_invalid,
        "errors": result.errors[:5],
    }


@router.post("/{campaign_id}/approve-job/{job_id}")
def approve_job(
    campaign_id: str,
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    runtime=Depends(get_runtime),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    ok = runtime.approve_job(
        job_id,
        tenant_id=current_user.tenant_id,
        engagement_id=campaign_id,
    )
    if not ok:
        raise HTTPException(400, "Job not found or not awaiting approval")
    job = store.get_job(job_id)
    payload = dict(getattr(job, "payload", None) or {}) if job else {}
    state = getattr(job, "state", None)
    sent = state == "succeeded"
    mailbox_id = payload.get("mailbox_id")
    result = getattr(job, "result", None) if job else None
    if isinstance(result, dict):
        mailbox_id = mailbox_id or result.get("mailbox_id")
    mailbox_flags = {}
    if mailbox_id:
        mailbox = store.get_mailbox(mailbox_id)
        if mailbox is not None:
            creds = dict(mailbox.credentials_json or {})
            mailbox_flags = {
                "has_refresh_token": bool(str(creds.get("refresh_token") or "").strip()),
                "has_access_token": bool(str(creds.get("token") or creds.get("access_token") or "").strip()),
                "mailbox_status": mailbox.status,
                "last_error": str(mailbox.last_error or "")[:160],
                "emails_sent_today": mailbox.emails_sent_today,
            }
    debug = {
        "job_id": job_id,
        "state": state,
        "sent": sent,
        "mailbox_id": mailbox_id,
        **mailbox_flags,
        "error": getattr(job, "last_error", None) if job and not sent else None,
    }
    from engine.debug_agent import agent_debug
    agent_debug("D", "campaigns.py:approve_job", "approve result", debug)
    return {
        "ok": True,
        "sent": sent,
        "state": state,
        "channel": payload.get("channel") or "email",
        "mailbox_id": mailbox_id,
        "error": getattr(job, "last_error", None) if job and not sent else None,
        "debug": debug,
    }


@router.post("/{campaign_id}/reject-job/{job_id}")
def reject_job(
    campaign_id: str,
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    runtime=Depends(get_runtime),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    ok = runtime.reject_job(
        job_id,
        reason="rejected via API",
        tenant_id=current_user.tenant_id,
        engagement_id=campaign_id,
    )
    if not ok:
        raise HTTPException(400, "Job not found or not awaiting approval")
    return {"ok": True}


class SnoozeJobRequest(BaseModel):
    until: str  # ISO 8601 datetime


@router.post("/{campaign_id}/snooze-job/{job_id}")
def snooze_job(
    campaign_id: str,
    job_id: str,
    body: SnoozeJobRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
    runtime=Depends(get_runtime),
):
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    from datetime import datetime
    try:
        until = datetime.fromisoformat(body.until)
    except (ValueError, TypeError):
        raise HTTPException(400, "until must be an ISO 8601 datetime")
    ok = runtime.snooze_job(job_id, until=until, tenant_id=current_user.tenant_id, engagement_id=campaign_id)
    if not ok:
        raise HTTPException(400, "Job not found or not awaiting approval")
    return {"ok": True, "snoozed_until": until.isoformat()}


@router.post("/{campaign_id}/rerun-job/{job_id}")
def rerun_job(
    campaign_id: str,
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    """Re-run the AI draft for a pending job (re-personalize + re-score)."""
    eng = store.get_engagement(campaign_id, tenant_id=current_user.tenant_id)
    if not eng:
        raise HTTPException(404, "Campaign not found")
    job = store.get_job(job_id)
    if job is None or job.engagement_id != campaign_id:
        raise HTTPException(404, "Job not found")
    if job.state != "awaiting_approval":
        raise HTTPException(400, "Job is not awaiting approval")

    from engine.adapters.email_merge import copy_quality_error, merge_email_copy
    from engine.llm.factory import build_llm_client
    from engine.llm.personalizer import personalize_outbound
    from engine.services.ai_email_critic import build_ai_critic
    from engine.services.deliverability_guardian import DeliverabilityGuardian

    payload = dict(job.payload or {})
    prospect = store.get_prospect(job.prospect_id) if job.prospect_id else None
    research, grounding = _evidence_terms(prospect)

    pres = personalize_outbound(
        offer=payload.get("offer", eng.offer or ""),
        name=payload.get("to_name") or payload.get("full_name") or "",
        company=payload.get("company", ""),
        title=payload.get("title", ""),
        research=research or payload.get("icp_fact") or "",
        subject_template=payload.get("subject_template", "Quick question for {first_name}"),
        body_template=payload.get("body_template", "Hi {first_name}, {offer}"),
        prospect_fields={
            "full_name": payload.get("full_name") or payload.get("to_name") or "",
            "first_name": payload.get("first_name") or "",
            "company": payload.get("company") or "",
            "title": payload.get("title") or "",
            "icp_fact": payload.get("icp_fact") or "",
            "raw": payload.get("raw") if isinstance(payload.get("raw"), dict) else {},
        },
        client=build_llm_client(),
    )
    payload["subject"] = pres.subject
    payload["body_text"] = pres.body_text
    payload["personalized"] = not pres.fallback_used
    payload["fallback_used"] = pres.fallback_used
    rendered_subject, rendered_body, rendered_html = merge_email_copy(payload)
    payload["subject"] = rendered_subject
    payload["body_text"] = rendered_body
    if rendered_html:
        payload["body_html"] = rendered_html
    quality_error = copy_quality_error(payload)
    if quality_error:
        payload["copy_quality_error"] = quality_error
    else:
        payload.pop("copy_quality_error", None)
    risk = DeliverabilityGuardian(llm_critic=build_ai_critic()).score(
        subject=rendered_subject,
        body=rendered_body,
        grounded_evidence=grounding or None,
        fallback_used=pres.fallback_used,
    )
    payload["deliverability_risk"] = risk.as_dict()
    job.payload = payload
    store.save_job(job)
    return {
        "ok": True,
        "subject": rendered_subject,
        "personalized": not pres.fallback_used,
        "copy_quality_error": quality_error,
        "deliverability_risk": risk.as_dict(),
    }


class EditJobRequest(BaseModel):
    subject: Optional[str] = None
    body_text: Optional[str] = None


@router.post("/{campaign_id}/edit-job/{job_id}")
def edit_job(
    campaign_id: str,
    job_id: str,
    body: EditJobRequest,
    current_user: CurrentUser = Depends(get_current_user),
    store=Depends(get_store),
):
    """Edit a pending draft's subject/body; re-scores deliverability after edit."""
    if not store.get_engagement(campaign_id, tenant_id=current_user.tenant_id):
        raise HTTPException(404, "Campaign not found")
    job = store.get_job(job_id)
    if job is None or job.engagement_id != campaign_id:
        raise HTTPException(404, "Job not found")
    if job.state != "awaiting_approval":
        raise HTTPException(400, "Job is not awaiting approval")

    from engine.adapters.email_merge import copy_quality_error, merge_email_copy
    from engine.services.ai_email_critic import build_ai_critic
    from engine.services.deliverability_guardian import DeliverabilityGuardian

    payload = dict(job.payload or {})
    if body.subject is not None:
        payload["subject"] = body.subject
    if body.body_text is not None:
        payload["body_text"] = body.body_text
    payload["edited"] = True
    rendered_subject, rendered_body, rendered_html = merge_email_copy(payload)
    payload["subject"] = rendered_subject
    payload["body_text"] = rendered_body
    if rendered_html:
        payload["body_html"] = rendered_html
    quality_error = copy_quality_error(payload)
    if quality_error:
        payload["copy_quality_error"] = quality_error
    else:
        payload.pop("copy_quality_error", None)
    risk = DeliverabilityGuardian(llm_critic=build_ai_critic()).score(
        subject=rendered_subject,
        body=rendered_body,
        fallback_used=bool(payload.get("fallback_used")),
    )
    payload["deliverability_risk"] = risk.as_dict()
    job.payload = payload
    store.save_job(job)
    return {
        "ok": True,
        "copy_quality_error": quality_error,
        "deliverability_risk": risk.as_dict(),
    }


def _evidence_terms(prospect: Any) -> tuple[str, list[str]]:
    """Return (research_string, grounding_terms) from a prospect's signal stack."""
    research = prospect.research if prospect and isinstance(prospect.research, dict) else {}
    stack = research.get("signal_stack") if isinstance(research, dict) else {}
    summaries: list[str] = []
    terms: list[str] = []
    if isinstance(stack, dict):
        for e in stack.get("evidence", []):
            if not isinstance(e, dict):
                continue
            s = str(e.get("summary", "")).strip()
            if s:
                summaries.append(s)
            for tok in str(e.get("signal_type", "")).replace("_", " ").split():
                if len(tok) > 2:
                    terms.append(tok)
            dom = str(e.get("company_domain", "")).split(".")[0]
            if dom:
                terms.append(dom)
    return "; ".join(summaries), terms
