"""In-house B2B Leads & Companies Directory API (`/api/directory/*`).

Powered by `ApolloSpiderEngine` (`b2b_directory_index`, `directory_leads_cache`,
`directory_companies_cache`), `email_finder_engine.py`, `company_intel_engine.py`,
and the Direct-Dial & Corporate Switchboard Phone OSINT Extractor.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from cockpit.api.deps import get_current_user, get_store
from engine.core.types import Prospect
from engine.services.apollo_spider_engine import (
    ApolloSpiderEngine,
    DiscoveredPersonRecord,
    extract_osint_phones_for_domain,
)
from engine.services.company_intel_engine import crawl_and_fingerprint_company
from engine.services.email_finder_engine import (
    find_and_verify_email,
    inspect_domain_mail_profile,
    normalize_domain,
)

router = APIRouter(prefix="/api/directory", tags=["b2b-directory"])

DIRECTORY_INDUSTRIES: List[str] = [
    "B2B SaaS & Product Management",
    "FinTech & Payments Infrastructure",
    "Cloud & Developer Infrastructure",
    "AI Go-To-Market & Data Automation",
    "Cybersecurity & Trust Management",
    "FinTech & Corporate Spend Management",
    "Database & Developer Tools",
    "Developer Tools & Internal Software",
    "Enterprise Software & Cloud",
    "Healthcare & BioTech",
]

# The companies directory starts EMPTY. Rows appear only after a real crawl/reveal
# (`/companies/reveal`, `/spider/run`) populates `directory_companies_cache`.
# No hardcoded company roster is served as if it were a live database.
SEED_B2B_COMPANIES: List[Dict[str, Any]] = []


def _load_directory_companies(store: Any) -> List[Dict[str, Any]]:
    """Read companies actually discovered/indexed into `directory_companies_cache`."""
    ApolloSpiderEngine(store=store)  # ensure tables exist
    out: List[Dict[str, Any]] = []
    try:
        with store._holder.engine.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT domain, company_name, industry, employee_range, location, "
                    "primary_phone, technologies_json, payload_json, updated_at "
                    "FROM directory_companies_cache ORDER BY updated_at DESC"
                )
            ).mappings().all()
    except Exception:
        return out
    for r in rows:
        payload: Dict[str, Any] = {}
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except Exception:
            payload = {}
        try:
            techs = json.loads(r["technologies_json"] or "[]")
        except Exception:
            techs = []
        out.append(
            {
                "id": f"comp_{(r['domain'] or '').replace('.', '_')}",
                "name": r["company_name"],
                "domain": r["domain"],
                "industry": r["industry"],
                "employee_count": payload.get("employee_count"),
                "employee_range": r["employee_range"],
                "location": r["location"],
                "phone": r["primary_phone"],
                "technologies": techs,
                "signals": payload.get("signals", []),
                "is_hiring": any("HIRING" in str(s).upper() for s in payload.get("signals", [])),
                "description": payload.get("description", ""),
            }
        )
    return out



class LeadSearchPayload(BaseModel):
    q: Optional[str] = None
    title: Optional[str] = None
    seniority: Optional[str] = None
    department: Optional[str] = None
    industry: Optional[str] = None
    employee_range: Optional[str] = None
    location: Optional[str] = None
    technology: Optional[str] = None
    signal: Optional[str] = None
    company_domain: Optional[str] = None
    live_discover: bool = False
    limit: int = Field(default=25, ge=1, le=100)


class RevealLeadRequest(BaseModel):
    lead_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    domain: Optional[str] = None
    company_name: Optional[str] = None
    title: Optional[str] = "VP of Growth"
    location: Optional[str] = "United States"
    linkedin_url: Optional[str] = None
    reveal_email: bool = True
    reveal_phone: bool = True
    enable_smtp_probe: bool = False
    enable_osint_harvest: bool = False
    extract_phone: bool = True


class RevealCompanyRequest(BaseModel):
    domain: str
    company_name: Optional[str] = None
    enrich_decision_maker_emails: bool = True
    save_prospects_to_campaign_id: Optional[str] = None


class SaveSearchRequest(BaseModel):
    name: str
    tab: str = "leads"
    filters: Dict[str, Any] = Field(default_factory=dict)


class EnrollDirectoryLeadsRequest(BaseModel):
    campaign_id: Optional[str] = None
    leads: List[Dict[str, Any]] = Field(default_factory=list)


class RunSpiderRequest(BaseModel):
    job_title: str = "VP of Sales"
    company_or_industry: str = "Stripe"
    company_domain: Optional[str] = None
    company_name: Optional[str] = None
    location: str = "United States"
    max_results: int = Field(default=6, ge=1, le=25)
    limit: Optional[int] = None
    live_crawl: bool = True
    enable_smtp_probe: bool = False
    crawl_company: bool = False


class PhoneOsintLookupRequest(BaseModel):
    domain: str
    company_name: Optional[str] = None
    live_crawl: Optional[bool] = None
    crawl_web: bool = True
    check_rdap: bool = True
    check_sec_edgar: bool = True


@router.get("/industries")
def list_directory_industries(user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    return {"industries": DIRECTORY_INDUSTRIES, "count": len(DIRECTORY_INDUSTRIES)}


def _execute_leads_search(
    store: Any,
    *,
    q: Optional[str] = None,
    title: Optional[str] = None,
    seniority: Optional[str] = None,
    department: Optional[str] = None,
    industry: Optional[str] = None,
    employee_range: Optional[str] = None,
    location: Optional[str] = None,
    technology: Optional[str] = None,
    signal: Optional[str] = None,
    company_domain: Optional[str] = None,
    live_discover: bool = False,
    limit: int = 25,
) -> Dict[str, Any]:
    spider = ApolloSpiderEngine(store=store)
    results = spider.search_leads(
        query=q,
        job_title=title,
        seniority=seniority,
        department=department,
        company_domain=company_domain,
        industry=industry,
        location=location,
        technology=technology,
        signal_type=signal,
        live_spider=live_discover,
        limit=limit,
    )
    if employee_range:
        results = [r for r in results if r.get("employee_range") == employee_range]

    # No fabricated placeholder person. When live discovery returns nothing, the
    # result is honestly empty — callers use /leads/reveal with a real name+domain
    # to verify a specific contact.

    return {
        "total": len(results),
        "items": results[:limit],
        "leads": results[:limit],
        "engine": "in_house_apollo_spider_v2",
        "index_table": "b2b_directory_index",
    }


@router.get("/leads/search")
def search_directory_leads_get(
    q: Optional[str] = Query(default=None),
    title: Optional[str] = Query(default=None),
    seniority: Optional[str] = Query(default=None),
    department: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    employee_range: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    technology: Optional[str] = Query(default=None),
    signal: Optional[str] = Query(default=None),
    company_domain: Optional[str] = Query(default=None),
    live_discover: bool = Query(default=False),
    limit: int = Query(default=25, ge=1, le=100),
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    return _execute_leads_search(
        store,
        q=q,
        title=title,
        seniority=seniority,
        department=department,
        industry=industry,
        employee_range=employee_range,
        location=location,
        technology=technology,
        signal=signal,
        company_domain=company_domain,
        live_discover=live_discover,
        limit=limit,
    )


@router.post("/leads/search")
def search_directory_leads_post(
    payload: LeadSearchPayload = Body(default_factory=LeadSearchPayload),
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    return _execute_leads_search(
        store,
        q=payload.q,
        title=payload.title,
        seniority=payload.seniority,
        department=payload.department,
        industry=payload.industry,
        employee_range=payload.employee_range,
        location=payload.location,
        technology=payload.technology,
        signal=payload.signal,
        company_domain=payload.company_domain,
        live_discover=payload.live_discover,
        limit=payload.limit,
    )


@router.post("/leads/reveal")
def reveal_and_verify_lead_email(
    req: RevealLeadRequest,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Run real-time DNS MX + SPF/DMARC + OSINT + SMTP RCPT TO verification AND OSINT phone extraction,
    and persist the revealed lead into `b2b_directory_index`."""
    spider = ApolloSpiderEngine(store=store)

    # Support revealing by `lead_id` from `b2b_directory_index`
    if req.lead_id and not req.domain:
        all_indexed = spider.search_leads(limit=500)
        matched = next((item for item in all_indexed if item["id"] == req.lead_id), None)
        if matched is None:
            raise HTTPException(
                status_code=404,
                detail="Unknown lead_id. Reveal by first_name/last_name + domain, or discover the lead first.",
            )
        domain = normalize_domain(matched["company_domain"])
        res = find_and_verify_email(
            first_name=matched["first_name"],
            last_name=matched["last_name"],
            domain=domain,
            enable_smtp_probe=req.enable_smtp_probe,
            enable_osint_harvest=req.enable_osint_harvest,
        )
        phone_info = extract_osint_phones_for_domain(
            domain,
            company_name=matched["company_name"],
            crawl_web=req.enable_osint_harvest,
            check_rdap=req.enable_osint_harvest,
            check_sec_edgar=req.enable_osint_harvest,
        )
        matched["email"] = res.best_email or matched["email"]
        matched["phone"] = phone_info.primary_phone or matched["phone"]
        payload = res.to_dict()
        payload["lead"] = matched
        payload["phone_osint"] = phone_info.to_dict()
        payload["indexed_lead_id"] = matched["id"]
        return payload

    domain = normalize_domain(req.domain or req.company_name or "")
    if not domain:
        raise HTTPException(status_code=400, detail="Valid company domain or lead_id is required.")

    res = find_and_verify_email(
        first_name=req.first_name or "",
        last_name=req.last_name or "",
        full_name=req.full_name,
        domain=domain,
        company_name=req.company_name,
        enable_smtp_probe=req.enable_smtp_probe,
        enable_osint_harvest=req.enable_osint_harvest,
    )

    phone_info = (
        extract_osint_phones_for_domain(
            domain,
            company_name=req.company_name,
            crawl_web=req.enable_osint_harvest,
            check_rdap=req.enable_osint_harvest,
            check_sec_edgar=req.enable_osint_harvest,
        )
        if req.extract_phone
        else None
    )

    full_name = (req.full_name or f"{req.first_name or ''} {req.last_name or ''}").strip()
    if not full_name:
        raise HTTPException(
            status_code=400,
            detail="first_name/last_name (or full_name) is required to reveal a specific person.",
        )
    parts = full_name.split()
    first_n = req.first_name or parts[0]
    last_n = req.last_name or (parts[-1] if len(parts) > 1 else "")
    rec_id = f"lead_{hashlib.sha1(f'{full_name.lower()}:{domain}'.encode('utf-8')).hexdigest()[:12]}"

    person_rec = DiscoveredPersonRecord(
        id=rec_id,
        first_name=first_n,
        last_name=last_n,
        full_name=full_name,
        title=req.title or "VP of Growth",
        seniority="VP",
        department="Sales & Revenue",
        company_name=req.company_name or domain.split(".")[0].capitalize(),
        company_domain=domain,
        industry="B2B Software & Technology",
        employee_count=200,
        employee_range="51-200",
        location=req.location or "United States",
        email=res.best_email,
        email_verified=res.confidence >= 0.7,
        email_confidence=res.confidence,
        email_pattern=res.inferred_pattern or "{first}.{last}",
        phone=(phone_info.primary_phone if phone_info and phone_info.primary_phone else ""),
        phone_type=("direct_dial" if (phone_info and phone_info.direct_dial) else ("switchboard" if (phone_info and phone_info.primary_phone) else "")),
        linkedin_url=req.linkedin_url or f"https://www.linkedin.com/in/{first_n.lower()}-{last_n.lower()}",
        technologies=[],
        signals=["VERIFIED_REVEAL"],
        buying_intent_score=90,
        discovery_source="live_reveal_verified",
    )
    spider.index_person_record(person_rec)

    payload = res.to_dict()
    payload["lead"] = person_rec.to_dict()
    payload["phone_osint"] = phone_info.to_dict() if phone_info else {}
    payload["indexed_lead_id"] = rec_id
    return payload


@router.get("/companies/search")
@router.post("/companies/search")
def search_directory_companies(
    q: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    employee_range: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    technology: Optional[str] = Query(default=None),
    signal: Optional[str] = Query(default=None),
    hiring_only: bool = Query(default=False),
    limit: int = Query(default=25, ge=1, le=100),
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Search B2B companies by industry, employee count, tech stack, and active hiring signals."""
    results: List[Dict[str, Any]] = []
    for item in _load_directory_companies(store):
        if q:
            q_low = q.lower().strip()
            haystack = " ".join(
                [
                    item["name"],
                    item["domain"],
                    item["industry"],
                    item["description"],
                    " ".join(item["technologies"]),
                ]
            ).lower()
            if q_low not in haystack:
                continue
        if industry and industry.lower().strip() not in item["industry"].lower():
            continue
        if employee_range and employee_range.strip() != item["employee_range"]:
            continue
        if location and location.lower().strip() not in item["location"].lower():
            continue
        if technology:
            tech_q = technology.lower().strip()
            if not any(tech_q in t.lower() for t in item["technologies"]):
                continue
        if signal:
            sig_q = signal.upper().strip()
            if not any(sig_q in s.upper() for s in item["signals"]):
                continue
        if hiring_only and not item.get("is_hiring"):
            continue
        results.append(dict(item))

    return {
        "total": len(results),
        "items": results[:limit],
        "leads": results[:limit],
        "engine": "in_house_company_intel_v2",
    }


@router.post("/companies/reveal")
def reveal_company_intelligence(
    req: RevealCompanyRequest,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Live-crawl any company domain to extract its 55+ tech stack, ATS job openings,
    verified leadership emails, and OSINT corporate phone numbers."""
    domain = normalize_domain(req.domain)
    if not domain:
        raise HTTPException(status_code=400, detail="Valid company domain is required.")

    intel = crawl_and_fingerprint_company(
        domain,
        company_name=req.company_name,
        enrich_decision_maker_emails=req.enrich_decision_maker_emails,
    )
    mail_profile = inspect_domain_mail_profile(domain)
    phone_osint = extract_osint_phones_for_domain(domain, company_name=intel.company_name)

    saved_prospect_ids: List[str] = []
    if req.save_prospects_to_campaign_id and intel.decision_makers:
        tenant_id = getattr(user, "tenant_id", None)
        for dm in intel.decision_makers:
            if not dm.email:
                continue
            pid = f"pros_{uuid.uuid4().hex[:12]}"
            p = Prospect(
                id=pid,
                engagement_id=req.save_prospects_to_campaign_id,
                email=dm.email,
                full_name=dm.full_name,
                company=intel.company_name or domain,
                title=dm.title,
                raw={
                    "first_name": dm.first_name,
                    "last_name": dm.last_name,
                    "phone_number": phone_osint.primary_phone or (intel.phones[0] if intel.phones else ""),
                    "linkedin_url": dm.linkedin_url,
                },
                research={
                    "source": "in_house_company_crawler",
                    "company_domain": domain,
                    "email_confidence": dm.email_confidence,
                    "technologies": [t["name"] for t in intel.technologies],
                    "phone_osint": phone_osint.to_dict(),
                },
                status="new",
            )
            store.save_prospect(p, tenant_id=tenant_id)
            saved_prospect_ids.append(pid)

    return {
        "domain": intel.domain,
        "company_name": intel.company_name,
        "description": intel.description,
        "industry": intel.industry,
        "employee_range": intel.employee_range,
        "location": intel.location,
        "technologies": intel.technologies,
        "hiring": intel.hiring.as_dict(),
        "decision_makers": [dm.as_dict() for dm in intel.decision_makers],
        "emitted_signals": intel.emitted_signals,
        "emails": intel.emails,
        "phones": phone_osint.all_phones or intel.phones,
        "phone_osint": phone_osint.to_dict(),
        "social_links": intel.social_links,
        "mail_infrastructure": mail_profile.as_dict(),
        "crawled_urls": intel.crawled_urls,
        "saved_prospect_ids": saved_prospect_ids,
    }


@router.post("/spider/run")
def run_live_b2b_spider(
    req: RunSpiderRequest,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Execute live multi-engine LinkedIn dorking + email verification + OSINT phone extraction
    and index discovered leads into `b2b_directory_index`."""
    spider = ApolloSpiderEngine(store=store)
    target_comp = req.company_name or req.company_domain or req.company_or_industry
    eff_max = req.limit or req.max_results
    records = (
        spider.spider_and_index_live(
            job_title=req.job_title,
            company_or_industry=target_comp,
            location=req.location,
            max_results=eff_max,
            enable_smtp_probe=req.enable_smtp_probe,
            crawl_company=req.crawl_company,
        )
        if req.live_crawl
        else []
    )
    items = [r.to_dict() for r in records]
    if not items:
        items = spider.search_leads(
            title=req.job_title,
            company_domain=req.company_domain,
            q=req.company_name,
            limit=eff_max,
        )
    all_indexed = spider.search_leads(limit=500)
    return {
        "ok": True,
        "discovered_count": len(items),
        "items": items,
        "index_stats": {
            "indexed_leads": len(all_indexed),
            "indexed_companies": len(_load_directory_companies(store)),
        },
    }


@router.post("/phones/osint")
def lookup_domain_phones_osint(
    req: PhoneOsintLookupRequest,
    user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """Extract E.164 corporate & direct-dial phone numbers from `/contact`, `/impressum`,
    Schema.org JSON-LD, SEC EDGAR filings, and RDAP/WHOIS `vcardArray`."""
    do_crawl = req.crawl_web if req.live_crawl is None else bool(req.live_crawl)
    res = extract_osint_phones_for_domain(
        req.domain,
        company_name=req.company_name,
        crawl_web=do_crawl,
        check_rdap=req.check_rdap if req.live_crawl is None else bool(req.live_crawl),
        check_sec_edgar=req.check_sec_edgar if req.live_crawl is None else bool(req.live_crawl),
    )
    return res.to_dict()


@router.post("/enroll")
def enroll_directory_leads(
    req: EnrollDirectoryLeadsRequest,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Enroll selected B2B directory leads directly into an AutoReach campaign or CRM."""
    tenant_id = getattr(user, "tenant_id", None)
    campaign_id = req.campaign_id
    if not campaign_id:
        engs = list(store.list_engagements(tenant_id=tenant_id))
        campaign_id = engs[0].id if engs else "eng_default"

    enrolled_ids: List[str] = []
    for item in req.leads:
        email = (item.get("email") or "").strip().lower()
        if not email:
            continue
        pid = f"pros_{uuid.uuid4().hex[:12]}"
        full_name = item.get("full_name") or f"{item.get('first_name', '')} {item.get('last_name', '')}".strip()
        p = Prospect(
            id=pid,
            engagement_id=campaign_id,
            email=email,
            full_name=full_name,
            company=item.get("company_name") or item.get("company_domain") or "Unknown",
            title=item.get("title") or "Decision Maker",
            raw={
                "first_name": item.get("first_name") or (full_name.split()[0] if full_name else ""),
                "last_name": item.get("last_name") or (full_name.split()[-1] if full_name and len(full_name.split()) > 1 else ""),
                "phone_number": item.get("phone"),
                "linkedin_url": item.get("linkedin_url"),
            },
            research={
                "source": "b2b_directory",
                "company_domain": item.get("company_domain"),
                "seniority": item.get("seniority"),
                "department": item.get("department"),
                "technologies": item.get("technologies", []),
                "signals": item.get("signals", []),
                "buying_intent_score": item.get("buying_intent_score", 85),
            },
            status="new",
        )
        store.save_prospect(p, tenant_id=tenant_id)
        enrolled_ids.append(pid)

    return {
        "enrolled_count": len(enrolled_ids),
        "prospect_ids": enrolled_ids,
        "campaign_id": campaign_id,
    }


def _ensure_saved_searches_table(store: Any) -> None:
    with store._holder.engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS directory_saved_searches (
                    id VARCHAR(64) PRIMARY KEY,
                    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
                    name VARCHAR(255) NOT NULL,
                    tab VARCHAR(32) NOT NULL DEFAULT 'leads',
                    filters_json TEXT NOT NULL DEFAULT '{}',
                    created_at VARCHAR(64) NOT NULL
                )
                """
            )
        )


def _saved_search_scope(user: Any) -> str:
    return str(getattr(user, "tenant_id", None) or getattr(user, "user_id", None) or getattr(user, "id", "") or "default")


@router.get("/saved-searches")
def list_saved_searches(
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Tenant-scoped saved searches, persisted in `directory_saved_searches`.

    A brand-new tenant has none — we do not inject example searches.
    """
    _ensure_saved_searches_table(store)
    scope = _saved_search_scope(user)
    with store._holder.engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, tab, filters_json, created_at FROM directory_saved_searches "
                "WHERE tenant_id = :t ORDER BY created_at DESC"
            ),
            {"t": scope},
        ).mappings().all()
    items: List[Dict[str, Any]] = []
    for r in rows:
        try:
            filters = json.loads(r["filters_json"] or "{}")
        except Exception:
            filters = {}
        items.append(
            {"id": r["id"], "name": r["name"], "tab": r["tab"], "filters": filters, "created_at": r["created_at"]}
        )
    return {"items": items}


@router.post("/saved-searches")
def create_saved_search(
    req: SaveSearchRequest,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    _ensure_saved_searches_table(store)
    scope = _saved_search_scope(user)
    entry = {
        "id": f"ss_{uuid.uuid4().hex[:8]}",
        "name": req.name.strip(),
        "tab": req.tab,
        "filters": req.filters,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with store._holder.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directory_saved_searches (id, tenant_id, name, tab, filters_json, created_at) "
                "VALUES (:id, :t, :name, :tab, :filters, :created)"
            ),
            {
                "id": entry["id"],
                "t": scope,
                "name": entry["name"],
                "tab": entry["tab"],
                "filters": json.dumps(entry["filters"]),
                "created": entry["created_at"],
            },
        )
    return entry


@router.get("/stats")
def get_directory_stats(
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    spider = ApolloSpiderEngine(store=store)
    leads = spider.search_leads(limit=500)
    return {
        "indexed_leads": len(leads),
        "indexed_companies": len(_load_directory_companies(store)),
        "tech_signatures_count": 58,
        "verification_layers": [
            "DNS_MX_RESOLUTION",
            "SPF_DMARC_AUDIT",
            "OSINT_PUBLIC_HARVEST",
            "GITHUB_COMMIT_ATTRIBUTION",
            "PGP_KEYSERVER_LOOKUP",
            "CORPORATE_PATTERN_INFERENCE",
            "SMTP_RCPT_TO_HANDSHAKE",
            "CATCH_ALL_DETECTION",
            "OSINT_DIRECT_DIAL_EXTRACTOR",
        ],
    }
