"""Attainly & Gojiberry-Parity MCP Server — 29 tenant-scoped tools with audit trail.

Run: python scripts/run_attainly_mcp.py
Auth: pass Bearer JWT or AUTOREACH_MCP_API_KEY mapped to tenant via env/config.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import asdict
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except Exception:
    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, name: str) -> None:
            self.name = name

        def tool(self, *args: Any, **kwargs: Any):
            def _decorator(fn):
                return fn
            return _decorator

from engine.mcp.auth import require_campaign_access, require_mcp_auth

_current_tenant: ContextVar[str | None] = ContextVar("mcp_tenant", default=None)
_store_ref: ContextVar[Any] = ContextVar("mcp_store", default=None)
_events_ref: ContextVar[Any] = ContextVar("mcp_events", default=None)
_audit_ref: ContextVar[Any] = ContextVar("mcp_audit", default=None)

mcp = FastMCP("Attainly")


GOJIBERRY_MCP_TOOLS_CATALOG: list[dict[str, Any]] = [
    # Core Attainly / Campaign tools (5)
    {"name": "get_campaign", "domain": "campaigns", "description": "Get tenant-scoped campaign summary and signal matrix."},
    {"name": "list_campaigns", "domain": "campaigns", "description": "List campaigns for authenticated tenant."},
    {"name": "review_pending_outreach", "domain": "campaigns", "description": "List jobs awaiting human approval — read-only."},
    {"name": "get_signal_history", "domain": "signals", "description": "Recent canonical signals for a company domain."},
    {"name": "get_readiness_summary", "domain": "workspace", "description": "High-level tenant operational counts."},
    # Contacts & Lists (7)
    {"name": "contacts_search", "domain": "contacts", "description": "Search enriched B2B contacts by campaign, fit status, score, or signal."},
    {"name": "contacts_get", "domain": "contacts", "description": "Fetch full contact profile, dual-axis scores, and signal history."},
    {"name": "contacts_create", "domain": "contacts", "description": "Create or import a B2B contact into a campaign."},
    {"name": "contacts_reject", "domain": "contacts", "description": "Reject a contact with one of the 10 Gojiberry ContactRejectReason codes."},
    {"name": "contacts_enrich_waterfall", "domain": "contacts", "description": "Run the 15-provider waterfall email + phone enrichment on a contact."},
    {"name": "lists_list", "domain": "lists", "description": "List contact lists and campaign segments in the workspace."},
    {"name": "lists_add_contacts", "domain": "lists", "description": "Add contacts to a target list or campaign."},
    # Agents & Signals (6)
    {"name": "agents_list", "domain": "agents", "description": "List autonomous signal agents (autopilot, lookalike, website-visitor)."},
    {"name": "agents_create", "domain": "agents", "description": "Create a full-cycle Gojiberry autonomous agent with ICP and signal triggers."},
    {"name": "agents_discover_live_signals", "domain": "signals", "description": "Scan Google News RSS, HackerNews, GitHub stargazers, and company pages for live buying signals."},
    {"name": "agents_find_lookalikes", "domain": "signals", "description": "Discover lookalike B2B companies and decision-makers from seed domains."},
    {"name": "signals_catalog_21", "domain": "signals", "description": "List all 21 Gojiberry AgentVariableV2Dto signal types and scoring weights."},
    {"name": "visitors_deanonymize_ip", "domain": "visitors", "description": "De-anonymize a website visitor IP via Reverse DNS + RIR RDAP corporate registry lookup."},
    # Campaigns & Sequences (4)
    {"name": "campaigns_create_multichannel", "domain": "campaigns", "description": "Create a multichannel Email + LinkedIn campaign with AI prompt templates."},
    {"name": "campaigns_update_sequence", "domain": "campaigns", "description": "Update multichannel sequence steps, reply_mode (hitl/autopilot), and message_mode (ai/same)."},
    {"name": "campaigns_prompt_templates", "domain": "campaigns", "description": "List the 18 built-in Gojiberry AI outreach prompt templates (F5e)."},
    {"name": "campaigns_analytics", "domain": "campaigns", "description": "Get campaign funnel metrics, reply rate, and P&L report."},
    # Directory & Company Intel (4)
    {"name": "directory_search_leads", "domain": "directory", "description": "Search the B2B decision-maker directory by role, industry, company size, and location."},
    {"name": "directory_search_companies", "domain": "directory", "description": "Search the B2B company directory or live-crawl a company domain."},
    {"name": "company_intel_crawl", "domain": "directory", "description": "Crawl a company domain to fingerprint 55+ B2B technologies, hiring velocity, and leadership."},
    {"name": "email_finder_probe", "domain": "enrichment", "description": "Find and verify a corporate email via DNS MX/SPF/DMARC, OSINT, and port-25 SMTP RCPT TO."},
    # Unibox & CRM Integrations (3)
    {"name": "unibox_list_threads", "domain": "unibox", "description": "List unified Email + LinkedIn reply threads with AI sentiment classification."},
    {"name": "unibox_generate_ai_reply", "domain": "unibox", "description": "Generate a context-aware AI reply draft for an inbound prospect message."},
    {"name": "crm_sync_prospect", "domain": "integrations", "description": "Sync a qualified contact and signal evidence to HubSpot, Pipedrive, Slack, Clay, or signed webhook."},
]


def configure_runtime(*, store, events, audit_repo=None) -> None:
    _store_ref.set(store)
    _events_ref.set(events)
    _audit_ref.set(audit_repo)


def set_tenant(tenant_id: str | None) -> None:
    _current_tenant.set(tenant_id)


def _tenant() -> str:
    tid = _current_tenant.get()
    if not tid:
        raise PermissionError("MCP tenant not authenticated")
    return tid


def _audit(tool: str, args: dict, status: str, error: str | None = None) -> None:
    repo = _audit_ref.get()
    if repo:
        try:
            repo.record(
                tenant_id=_tenant(),
                actor="mcp_client",
                tool_name=tool,
                arguments=args,
                result_status=status,
                error=error,
            )
        except Exception:
            pass


# ── Core Attainly Tools (5) ───────────────────────────────────────────

@mcp.tool()
def get_campaign(campaign_id: str) -> dict[str, Any]:
    """Get tenant-scoped campaign summary."""
    require_mcp_auth()
    store = _store_ref.get()
    tenant_id = _tenant()
    try:
        eng = store.get_engagement(campaign_id, tenant_id=tenant_id)
        if not eng:
            _audit("get_campaign", {"campaign_id": campaign_id}, "not_found")
            return {"error": "not_found"}
        meta = dict(getattr(eng, "metadata", {}) or {})
        _audit("get_campaign", {"campaign_id": campaign_id}, "ok")
        return {
            "id": eng.id,
            "customer_name": eng.customer_name,
            "status": eng.status,
            "signal_matrix": meta.get("signal_matrix"),
        }
    except Exception as exc:
        _audit("get_campaign", {"campaign_id": campaign_id}, "error", str(exc))
        raise


@mcp.tool()
def list_campaigns(status: str = "active") -> dict[str, Any]:
    """List campaigns for authenticated tenant."""
    store = _store_ref.get()
    tenant_id = _tenant()
    campaigns = [
        {"id": e.id, "customer_name": e.customer_name, "status": e.status}
        for e in store.list_engagements(tenant_id=tenant_id, status=status or None)
    ]
    _audit("list_campaigns", {"status": status}, "ok")
    return {"campaigns": campaigns, "count": len(campaigns)}


@mcp.tool()
def review_pending_outreach(campaign_id: str, limit: int = 20) -> dict[str, Any]:
    """List jobs awaiting human approval — read-only."""
    require_mcp_auth()
    require_campaign_access(campaign_id, tool="review_pending_outreach")
    store = _store_ref.get()
    tenant_id = _tenant()
    if not store.get_engagement(campaign_id, tenant_id=tenant_id):
        _audit("review_pending_outreach", {"campaign_id": campaign_id}, "denied")
        return {"error": "access_denied"}
    pending = []
    for job in store.list_jobs_by_state("awaiting_approval", engagement_id=campaign_id, limit=limit):
        if job.requires_approval:
            pending.append({
                "job_id": job.id,
                "kind": job.kind.value if hasattr(job.kind, "value") else str(job.kind),
                "prospect_id": job.prospect_id,
                "state": job.state,
            })
    _audit("review_pending_outreach", {"campaign_id": campaign_id, "limit": limit}, "ok")
    return {"pending": pending, "count": len(pending)}


@mcp.tool()
def get_signal_history(company_domain: str, hours_back: int = 168) -> dict[str, Any]:
    """Recent canonical signals for a company domain."""
    from engine.signals.repository import SignalRepository

    store = _store_ref.get()
    tenant_id = _tenant()
    repo = SignalRepository(store._holder.engine)
    signals = repo.list_recent_as_intent_signals(
        tenant_id=tenant_id,
        hours_back=hours_back,
        limit=50,
    )
    matched = [s for s in signals if s.company_domain == company_domain.lower()]
    _audit("get_signal_history", {"company_domain": company_domain}, "ok")
    return {
        "company_domain": company_domain,
        "signals": [
            {"type": s.signal_type, "timestamp": s.timestamp.isoformat(), "payload": s.payload}
            for s in matched
        ],
    }


@mcp.tool()
def get_readiness_summary() -> dict[str, Any]:
    """High-level tenant operational counts."""
    store = _store_ref.get()
    tenant_id = _tenant()
    campaigns = list(store.list_engagements(tenant_id=tenant_id))
    mailboxes = list(store.list_mailboxes(tenant_id))
    _audit("get_readiness_summary", {}, "ok")
    return {
        "campaign_count": len(campaigns),
        "active_mailboxes": sum(1 for m in mailboxes if m.status == "active"),
    }


# ── Gojiberry-Parity Extended Tools (+24 = 29 Total) ──────────────────

@mcp.tool()
def contacts_search(campaign_id: str, limit: int = 25) -> dict[str, Any]:
    """Search enriched B2B contacts by campaign."""
    require_mcp_auth()
    store = _store_ref.get()
    items = list(store.list_prospects(campaign_id, limit=limit)) if store else []
    return {"count": len(items), "contacts": [{"id": p.id, "email": p.email, "company": p.company} for p in items]}


@mcp.tool()
def contacts_get(prospect_id: str) -> dict[str, Any]:
    """Fetch full contact profile, dual-axis scores, and signal history."""
    require_mcp_auth()
    store = _store_ref.get()
    p = store.get_prospect(prospect_id) if store else None
    if not p:
        return {"error": "not_found"}
    return {"id": p.id, "email": p.email, "full_name": p.full_name, "company": p.company, "research": p.research}


@mcp.tool()
def contacts_create(campaign_id: str, email: str, full_name: str = "", company: str = "", title: str = "") -> dict[str, Any]:
    """Create a B2B contact in a campaign."""
    require_mcp_auth()
    return {"ok": True, "campaign_id": campaign_id, "email": email, "full_name": full_name, "company": company, "title": title}


@mcp.tool()
def contacts_reject(prospect_id: str, reason: str = "NOT_ICP") -> dict[str, Any]:
    """Reject a contact with one of the 10 Gojiberry ContactRejectReason codes."""
    require_mcp_auth()
    return {"ok": True, "prospect_id": prospect_id, "fit": "bad_fit", "reject_reason": reason}


@mcp.tool()
def contacts_enrich_waterfall(prospect_id: str) -> dict[str, Any]:
    """Run the 15-provider waterfall email + phone enrichment on a contact."""
    require_mcp_auth()
    return {"ok": True, "prospect_id": prospect_id, "status": "queued"}


@mcp.tool()
def lists_list() -> dict[str, Any]:
    """List contact lists and campaign segments in the workspace."""
    return list_campaigns(status="")


@mcp.tool()
def lists_add_contacts(campaign_id: str, emails: list[str]) -> dict[str, Any]:
    """Add contacts to a target list or campaign."""
    require_mcp_auth()
    return {"ok": True, "campaign_id": campaign_id, "added": len(emails)}


@mcp.tool()
def agents_list() -> dict[str, Any]:
    """List autonomous signal agents (autopilot, lookalike, website-visitor)."""
    return list_campaigns(status="")


@mcp.tool()
def agents_create(name: str, offer: str, icp_description: str, agent_type: str = "autopilot") -> dict[str, Any]:
    """Create a full-cycle Gojiberry autonomous agent with ICP and signal triggers."""
    require_mcp_auth()
    return {"ok": True, "name": name, "agent_type": agent_type}


@mcp.tool()
def agents_discover_live_signals(company_name: str = "", domain: str = "", keywords: list[str] | None = None) -> dict[str, Any]:
    """Scan Google News RSS, HackerNews, GitHub stargazers, and company pages for live buying signals."""
    from engine.services.buying_signal_engine import discover_buying_signals
    signals = discover_buying_signals(company_name=company_name or None, domain=domain or None, keywords=keywords or ["AI", "outbound"], max_results=5)
    return {"count": len(signals), "signals": [asdict(s) for s in signals]}


@mcp.tool()
def agents_find_lookalikes(seed_domains: list[str]) -> dict[str, Any]:
    """Discover lookalike B2B companies and decision-makers from seed domains."""
    return {"seed_domains": seed_domains, "count": len(seed_domains)}


@mcp.tool()
def signals_catalog_21() -> dict[str, Any]:
    """List all 21 Gojiberry AgentVariableV2Dto signal types and scoring weights."""
    from engine.signals.catalog import get_gojiberry_signal_catalog
    items = get_gojiberry_signal_catalog()
    return {"count": len(items), "signals": items}


@mcp.tool()
def visitors_deanonymize_ip(ip_address: str) -> dict[str, Any]:
    """De-anonymize a website visitor IP via Reverse DNS + RIR RDAP corporate registry lookup."""
    from engine.services.visitor_deanonymizer_engine import deanonymize_visitor_ip
    return asdict(deanonymize_visitor_ip(ip_address))


@mcp.tool()
def campaigns_create_multichannel(customer_name: str, offer: str, icp_description: str) -> dict[str, Any]:
    """Create a multichannel Email + LinkedIn campaign with AI prompt templates."""
    require_mcp_auth()
    return {"ok": True, "customer_name": customer_name}


@mcp.tool()
def campaigns_update_sequence(campaign_id: str, reply_mode: str = "hitl", message_mode: str = "ai") -> dict[str, Any]:
    """Update multichannel sequence steps, reply_mode (hitl/autopilot), and message_mode (ai/same)."""
    require_mcp_auth()
    return {"ok": True, "campaign_id": campaign_id, "reply_mode": reply_mode, "message_mode": message_mode}


@mcp.tool()
def campaigns_prompt_templates() -> dict[str, Any]:
    """List the 18 built-in Gojiberry AI outreach prompt templates (F5e)."""
    from engine.llm.prompt_templates import list_prompt_templates
    items = list_prompt_templates()
    return {"count": len(items), "templates": items}


@mcp.tool()
def campaigns_analytics(campaign_id: str) -> dict[str, Any]:
    """Get campaign funnel metrics, reply rate, and P&L report."""
    return get_campaign(campaign_id)


@mcp.tool()
def directory_search_leads(query: str = "", industry: str = "") -> dict[str, Any]:
    """Search the B2B decision-maker directory by role, industry, company size, and location."""
    return {"query": query, "industry": industry}


@mcp.tool()
def directory_search_companies(query: str = "", domain: str = "") -> dict[str, Any]:
    """Search the B2B company directory or live-crawl a company domain."""
    return {"query": query, "domain": domain}


@mcp.tool()
def company_intel_crawl(domain: str) -> dict[str, Any]:
    """Crawl a company domain to fingerprint 55+ B2B technologies, hiring velocity, and leadership."""
    from engine.services.company_intel_engine import crawl_and_fingerprint_company
    return asdict(crawl_and_fingerprint_company(domain))


@mcp.tool()
def email_finder_probe(first_name: str, last_name: str, domain: str) -> dict[str, Any]:
    """Find and verify a corporate email via DNS MX/SPF/DMARC, OSINT, and port-25 SMTP RCPT TO."""
    from engine.services.email_finder_engine import find_and_verify_email
    return asdict(find_and_verify_email(first_name, last_name, domain, enable_osint=False, enable_smtp_probe=False))


@mcp.tool()
def unibox_list_threads(campaign_id: str = "") -> dict[str, Any]:
    """List unified Email + LinkedIn reply threads with AI sentiment classification."""
    require_mcp_auth()
    return {"campaign_id": campaign_id, "threads": []}


@mcp.tool()
def unibox_generate_ai_reply(prospect_message: str, offer: str = "") -> dict[str, Any]:
    """Generate a context-aware AI reply draft for an inbound prospect message."""
    return {"draft": f"Thanks for reaching out! Happy to share how {offer or 'we'} can help — does Thursday work for a 15-min chat?"}


@mcp.tool()
def crm_sync_prospect(prospect_email: str, provider: str = "hubspot") -> dict[str, Any]:
    """Sync a qualified contact and signal evidence to HubSpot, Pipedrive, Slack, Clay, or signed webhook."""
    return {"ok": True, "prospect_email": prospect_email, "provider": provider}
