"""ICP people discovery — SourceAgent-style web search onto a campaign.

Generic for any ICP. Uses job titles + search keywords + industries +
locations to dork public LinkedIn /in/ pages (and optional company /team
pages). Does not scrape private CSVs and does not invent fake VPs.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from engine.core.types import Prospect
from engine.services.accounts import normalize_company_domain, upsert_account
from engine.services.email_finder_engine import find_and_verify_email, normalize_domain

logger = logging.getLogger(__name__)

FIRST_RUN_CAP = 20
MIN_DISCOVERY_CAP = 15
MAX_DISCOVERY_CAP = 25
# Gojiberry event signals (HIRING / FUNDING / job-change) run at most once
# every 72 hours per Source Agent. Stamp last_complete_at so a later beat
# refresh can honor that throttle without blocking Launch or Find buyers.
EVENT_SIGNAL_THROTTLE = timedelta(hours=72)
NEEDS_ICP_MESSAGE = (
    "No buyer titles or keywords yet. Add a product blurb or job titles, then find buyers."
)
EMPTY_MESSAGE = (
    "No public buyers matched this ICP. Add a product blurb or titles and try again."
)
RUNNING_MESSAGE = "Finding buyers from your ICP…"


@dataclass
class DiscoveredBuyer:
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    title: str = ""
    company: str = ""
    company_domain: str = ""
    location: str = ""
    linkedin_url: str = ""
    email: str = ""
    email_confidence: float = 0.0
    discovery_source: str = "icp_people_search"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "title": self.title,
            "company": self.company,
            "company_domain": self.company_domain,
            "location": self.location,
            "linkedin_url": self.linkedin_url,
            "email": self.email,
            "email_confidence": self.email_confidence,
            "discovery_source": self.discovery_source,
        }


@dataclass
class PeopleDiscoveryResult:
    people: List[DiscoveredBuyer] = field(default_factory=list)
    queries: List[str] = field(default_factory=list)
    status: str = "empty"  # needs_icp | empty | complete | error
    message: str = EMPTY_MESSAGE
    cap: int = FIRST_RUN_CAP

    def to_dict(self) -> Dict[str, Any]:
        return {
            "people": [p.to_dict() for p in self.people],
            "queries": list(self.queries),
            "status": self.status,
            "message": self.message,
            "cap": self.cap,
            "found": len(self.people),
            "with_email": sum(1 for p in self.people if p.email),
        }


def clamp_discovery_cap(raw: Any = None) -> int:
    try:
        value = int(raw) if raw is not None else FIRST_RUN_CAP
    except (TypeError, ValueError):
        value = FIRST_RUN_CAP
    return max(MIN_DISCOVERY_CAP, min(MAX_DISCOVERY_CAP, value))


def normalize_icp_list(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        parts = [p.strip() for p in values.replace(";", ",").split(",")]
        return [p for p in parts if p]
    out: List[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _usable_osint_email(result: Any) -> str:
    """Keep email only when OSINT/SMTP actually found one — not a permutation guess."""
    if result is None:
        return ""
    email = str(getattr(result, "email", "") or getattr(result, "best_email", "") or "").strip().lower()
    if not email or "@" not in email:
        return ""
    status = str(getattr(result, "status", "") or "")
    method = str(getattr(result, "verification_method", "") or "")
    if method in ("public_osint_exact_match", "smtp_rcpt_250") or status == "verified":
        return email
    if status == "pattern_matched" and float(getattr(result, "confidence", 0) or 0) >= 0.9:
        return email
    return ""


def _buyer_from_raw(raw: Dict[str, Any]) -> Optional[DiscoveredBuyer]:
    linkedin_url = str(raw.get("linkedin_url") or "").strip()
    full_name = str(raw.get("full_name") or "").strip()
    first_name = str(raw.get("first_name") or "").strip()
    last_name = str(raw.get("last_name") or "").strip()
    if not first_name and full_name:
        parts = [p for p in full_name.split() if p]
        first_name = parts[0] if parts else ""
        last_name = parts[-1] if len(parts) > 1 else ""
    if not full_name:
        full_name = f"{first_name} {last_name}".strip()
    if not linkedin_url or not first_name or not last_name:
        return None
    title = str(raw.get("title") or "").strip()
    company = str(raw.get("company_name") or raw.get("company") or "").strip()
    domain = normalize_domain(raw.get("company_domain") or "") or ""
    return DiscoveredBuyer(
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        title=title,
        company=company,
        company_domain=domain,
        location=str(raw.get("location") or "").strip(),
        linkedin_url=linkedin_url.split("?")[0].rstrip("/"),
        email=str(raw.get("email") or "").strip().lower(),
        email_confidence=float(raw.get("email_confidence") or 0),
        discovery_source=str(raw.get("discovery_source") or "icp_people_search"),
    )


def _people_from_team_pages(
    domains: List[str],
    *,
    job_titles: List[str],
    max_people: int,
    exclude_domain: str = "",
) -> List[DiscoveredBuyer]:
    if not domains or max_people <= 0:
        return []
    from engine.services.company_intel_engine import crawl_and_fingerprint_company

    found: List[DiscoveredBuyer] = []
    titles_l = [t.lower() for t in job_titles]
    exclude = (exclude_domain or "").lower()
    for domain in domains[:3]:
        if not domain or domain.lower() == exclude:
            continue
        try:
            intel = crawl_and_fingerprint_company(
                domain,
                enrich_decision_maker_emails=False,
                max_subpages=4,
            )
        except Exception:
            logger.exception("team-page crawl failed for %s", domain)
            continue
        for dm in intel.decision_makers:
            if not dm.linkedin_url:
                continue
            title = (dm.title or "").strip()
            if titles_l and title:
                hay = title.lower()
                if not any(t in hay or hay in t for t in titles_l):
                    continue
            buyer = _buyer_from_raw(
                {
                    "first_name": dm.first_name,
                    "last_name": dm.last_name,
                    "full_name": dm.full_name,
                    "title": title,
                    "company_name": intel.company_name or domain,
                    "company_domain": domain,
                    "linkedin_url": dm.linkedin_url,
                    "discovery_source": "company_team_page",
                }
            )
            if buyer:
                found.append(buyer)
            if len(found) >= max_people:
                return found
    return found


def discover_people_for_icp(
    *,
    job_titles: Optional[List[str]] = None,
    search_keywords: Optional[List[str]] = None,
    industries: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    company_domains: Optional[List[str]] = None,
    exclude_domain: str = "",
    max_results: int = FIRST_RUN_CAP,
    spider: Any = None,
    resolve_emails: bool = True,
    crawl_team_pages: bool = True,
    email_finder: Callable[..., Any] = find_and_verify_email,
) -> PeopleDiscoveryResult:
    """Search the public web for buyers matching this ICP. Empty stays empty."""
    cap = clamp_discovery_cap(max_results)
    titles = normalize_icp_list(job_titles)
    keywords = normalize_icp_list(search_keywords)
    industries = normalize_icp_list(industries)
    locations = normalize_icp_list(locations)
    known_domains = [normalize_domain(d) or "" for d in (company_domains or [])]
    known_domains = [d for d in known_domains if d]
    exclude = normalize_domain(exclude_domain) or ""

    if not titles and not keywords and not industries:
        return PeopleDiscoveryResult(status="needs_icp", message=NEEDS_ICP_MESSAGE, cap=cap)

    if os.getenv("PYTEST_CURRENT_TEST"):
        crawl_team_pages = False
        if email_finder is find_and_verify_email:
            resolve_emails = False
        if spider is None:
            # Never dork the public web inside pytest unless a test injects a spider.
            return PeopleDiscoveryResult(status="empty", message=EMPTY_MESSAGE, cap=cap)

    if spider is None:
        from engine.services.apollo_spider_engine import ApolloSpiderEngine

        spider = ApolloSpiderEngine(store=None)

    raw_hits: List[Dict[str, Any]] = []
    if hasattr(spider, "discover_icp_people"):
        raw_hits = list(
            spider.discover_icp_people(
                job_titles=titles,
                search_keywords=keywords,
                industries=industries,
                locations=locations,
                max_results=cap,
                invent_missing_title=False,
            )
            or []
        )
    elif hasattr(spider, "spider_and_index_live"):
        # Test doubles often stub spider_and_index_live with a fixed list.
        live_title = titles[0] if titles else (keywords[0] if keywords else "")
        live_industry = industries[0] if industries else (keywords[0] if keywords else "")
        live_loc = locations[0] if locations else "United States"
        live = spider.spider_and_index_live(
            job_title=live_title,
            company_or_industry=live_industry,
            location=live_loc,
            max_results=cap,
        )
        for item in live or []:
            raw_hits.append(item.to_dict() if hasattr(item, "to_dict") else dict(item))

    buyers: List[DiscoveredBuyer] = []
    seen_urls: set[str] = set()
    for raw in raw_hits:
        buyer = _buyer_from_raw(raw if isinstance(raw, dict) else {})
        if not buyer or buyer.linkedin_url in seen_urls:
            continue
        if exclude and buyer.company_domain.lower() == exclude.lower():
            continue
        seen_urls.add(buyer.linkedin_url)
        buyers.append(buyer)
        if len(buyers) >= cap:
            break

    if crawl_team_pages and len(buyers) < cap:
        team_domains = list(dict.fromkeys(
            [*(b.company_domain for b in buyers if b.company_domain), *known_domains]
        ))
        for extra in _people_from_team_pages(
            team_domains,
            job_titles=titles,
            max_people=cap - len(buyers),
            exclude_domain=exclude,
        ):
            if extra.linkedin_url in seen_urls:
                continue
            seen_urls.add(extra.linkedin_url)
            buyers.append(extra)
            if len(buyers) >= cap:
                break

    if resolve_emails:
        for buyer in buyers:
            if buyer.email or not buyer.company_domain:
                continue
            try:
                found = email_finder(
                    buyer.first_name,
                    buyer.last_name,
                    buyer.company_domain,
                    enable_smtp_probe=False,
                    discover_public=True,
                )
            except Exception:
                logger.exception("email OSINT failed for %s", buyer.full_name)
                continue
            email = _usable_osint_email(found)
            if email:
                buyer.email = email
                buyer.email_confidence = float(getattr(found, "confidence", 0) or 0)

    queries = [h.get("discovery_query") for h in raw_hits if isinstance(h, dict) and h.get("discovery_query")]
    if not buyers:
        return PeopleDiscoveryResult(
            people=[],
            queries=[q for q in queries if q],
            status="empty",
            message=EMPTY_MESSAGE,
            cap=cap,
        )
    return PeopleDiscoveryResult(
        people=buyers[:cap],
        queries=[q for q in queries if q],
        status="complete",
        message=f"Found {min(len(buyers), cap)} buyers from public people search.",
        cap=cap,
    )


_GENERIC_ICP_TEXT = frozenset({"i", "icp", "n/a", "na", "none", "unknown", "test", "o"})


def _usable_icp_text(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) < 8 or text.lower() in _GENERIC_ICP_TEXT:
        return ""
    return text


def icp_from_engagement(eng: Any) -> Dict[str, List[str]]:
    metadata = dict(getattr(eng, "metadata", {}) or {})
    filters = dict(getattr(eng, "icp_filters", {}) or {})
    titles = normalize_icp_list(
        metadata.get("target_job_titles")
        or metadata.get("job_titles")
        or filters.get("target_job_titles")
        or filters.get("job_titles")
    )
    adjacent = normalize_icp_list(
        metadata.get("adjacent_job_titles") or filters.get("adjacent_job_titles")
    )
    for title in adjacent:
        if title not in titles:
            titles.append(title)
    keywords = normalize_icp_list(metadata.get("search_keywords") or filters.get("search_keywords"))
    industries = normalize_icp_list(
        metadata.get("target_industries") or filters.get("target_industries") or filters.get("industries")
    )
    locations = normalize_icp_list(
        metadata.get("target_locations") or filters.get("target_locations") or filters.get("locations")
    )
    if not titles and not keywords and not industries:
        fallback = _usable_icp_text(getattr(eng, "icp_description", ""))
        if fallback:
            keywords = [fallback]
    return {
        "job_titles": titles,
        "search_keywords": keywords,
        "industries": industries,
        "locations": locations,
        "company_types": normalize_icp_list(
            metadata.get("target_company_types") or filters.get("target_company_types")
        ),
    }


def _stamp_discovery_metadata(eng: Any, payload: Dict[str, Any]) -> Any:
    metadata = dict(getattr(eng, "metadata", {}) or {})
    current = dict(metadata.get("people_discovery") or {})
    current.update(payload)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    metadata["people_discovery"] = current
    return replace(eng, metadata=metadata)


def _prospect_id_for(*, tenant_id: str, campaign_id: str, buyer: DiscoveredBuyer) -> str:
    seed = buyer.linkedin_url or f"{buyer.full_name}|{buyer.company_domain}|{buyer.email}"
    digest = hashlib.sha1(f"{tenant_id}|{campaign_id}|{seed}".encode("utf-8")).hexdigest()[:20]
    return f"p_disc_{digest}"


def persist_discovered_people(
    store: Any,
    *,
    tenant_id: str,
    campaign_id: str,
    people: List[DiscoveredBuyer],
    cap: int = FIRST_RUN_CAP,
    plan: str = "free",
) -> Dict[str, Any]:
    cap = clamp_discovery_cap(cap)
    from engine.policies.lead_caps import count_tenant_leads
    from engine.policies.plan_limits import get_plan_limits

    remaining = max(0, int(get_plan_limits(plan).max_leads_total) - count_tenant_leads(store, tenant_id))
    created = 0
    with_email = 0
    skipped_existing = 0
    persisted: List[Dict[str, Any]] = []
    for buyer in people[:cap]:
        if created >= remaining:
            break
        pid = _prospect_id_for(tenant_id=tenant_id, campaign_id=campaign_id, buyer=buyer)
        if store.get_prospect(pid) is not None:
            skipped_existing += 1
            continue
        domain = normalize_company_domain(buyer.company_domain) or buyer.company_domain
        account = upsert_account(
            store,
            tenant_id=tenant_id,
            engagement_id=campaign_id,
            company_domain=domain or "",
            company_name=buyer.company or domain,
        )
        research: Dict[str, Any] = {
            "source": "icp_people_discovery",
            "discovery_source": buyer.discovery_source,
            "linkedin_url": buyer.linkedin_url,
            "company_domain": domain,
            "email_confidence": buyer.email_confidence,
            "location": buyer.location,
        }
        if account is not None:
            research["account_id"] = account.id
            research["company_domain"] = account.company_domain
        email = (buyer.email or "").strip().lower() or None
        store.save_prospect(
            Prospect(
                id=pid,
                engagement_id=campaign_id,
                email=email,
                full_name=buyer.full_name or None,
                company=buyer.company or domain,
                title=buyer.title or None,
                raw={
                    "first_name": buyer.first_name,
                    "last_name": buyer.last_name,
                    "linkedin_url": buyer.linkedin_url,
                    "location": buyer.location,
                },
                research=research,
                status="new",
            ),
            tenant_id=tenant_id,
        )
        created += 1
        if email:
            with_email += 1
        persisted.append(
            {
                "id": pid,
                "full_name": buyer.full_name,
                "title": buyer.title,
                "company": buyer.company,
                "linkedin_url": buyer.linkedin_url,
                "email": email,
                "contactable": bool(email),
            }
        )
    return {
        "created": created,
        "with_email": with_email,
        "without_email": created - with_email,
        "skipped_existing": skipped_existing,
        "remaining_capacity": remaining,
        "prospects": persisted,
    }


def run_campaign_people_discovery(
    store: Any,
    *,
    tenant_id: str,
    campaign_id: str,
    cap: Optional[int] = None,
    spider: Any = None,
    resolve_emails: bool = True,
    crawl_team_pages: bool = True,
) -> Dict[str, Any]:
    """Discover buyers for one campaign and persist them. Never fabricates VPs."""
    eng = store.get_engagement(campaign_id, tenant_id=tenant_id)
    if eng is None:
        return {"ok": False, "status": "error", "message": "Campaign not found", "created": 0}

    icp = icp_from_engagement(eng)
    metadata = dict(eng.metadata or {})
    cap = clamp_discovery_cap(cap or metadata.get("discovery_cap") or FIRST_RUN_CAP)
    exclude = str(metadata.get("source_website") or "")
    tenant = store.get_tenant(tenant_id) if hasattr(store, "get_tenant") else None
    plan = getattr(tenant, "plan", None) or "free"

    running = _stamp_discovery_metadata(
        eng,
        {
            "status": "running",
            "message": RUNNING_MESSAGE,
            "cap": cap,
            "found": 0,
            "with_email": 0,
        },
    )
    store.save_engagement(running, tenant_id=tenant_id)

    try:
        result = discover_people_for_icp(
            job_titles=icp["job_titles"],
            search_keywords=icp["search_keywords"],
            industries=icp["industries"],
            locations=icp["locations"],
            exclude_domain=exclude,
            max_results=cap,
            spider=spider,
            resolve_emails=resolve_emails,
            crawl_team_pages=crawl_team_pages,
        )
        persist = persist_discovered_people(
            store,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            people=result.people,
            cap=cap,
            plan=plan,
        )
        status = result.status
        message = result.message
        if status == "complete" and persist["created"] == 0 and persist["skipped_existing"] == 0:
            if persist.get("remaining_capacity", 1) <= 0:
                status = "error"
                message = "Buyer search found people, but this plan has no remaining lead capacity."
            else:
                status = "empty"
                message = EMPTY_MESSAGE
        latest = store.get_engagement(campaign_id, tenant_id=tenant_id) or running
        stamped = _stamp_discovery_metadata(
            latest,
            {
                "status": status,
                "message": message,
                "cap": cap,
                "found": persist["created"] + persist["skipped_existing"],
                "created": persist["created"],
                "with_email": persist["with_email"],
                "queries": result.queries[:8],
                "last_complete_at": datetime.now(timezone.utc).isoformat(),
                "event_signal_throttle_hours": int(EVENT_SIGNAL_THROTTLE.total_seconds() // 3600),
            },
        )
        store.save_engagement(stamped, tenant_id=tenant_id)
        return {
            "ok": True,
            "campaign_id": campaign_id,
            "status": status,
            "message": message,
            "cap": cap,
            **persist,
            "people_discovery": dict((stamped.metadata or {}).get("people_discovery") or {}),
        }
    except Exception as exc:
        logger.exception("people discovery failed campaign=%s", campaign_id)
        latest = store.get_engagement(campaign_id, tenant_id=tenant_id) or running
        failed = _stamp_discovery_metadata(
            latest,
            {
                "status": "error",
                "message": "Buyer search failed. Try Find buyers again.",
                "cap": cap,
                "error": str(exc)[:300],
            },
        )
        store.save_engagement(failed, tenant_id=tenant_id)
        return {
            "ok": False,
            "campaign_id": campaign_id,
            "status": "error",
            "message": "Buyer search failed. Try Find buyers again.",
            "created": 0,
        }


def celery_worker_enabled() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return bool((os.getenv("REDIS_URL") or "").strip())


def kickoff_campaign_people_discovery(
    store: Any,
    *,
    tenant_id: str,
    campaign_id: str,
    cap: Optional[int] = None,
    spider: Any = None,
) -> Dict[str, Any]:
    """Queue on the worker when Redis is configured; otherwise run inline."""
    eng = store.get_engagement(campaign_id, tenant_id=tenant_id)
    if eng is None:
        return {"ok": False, "status": "error", "message": "Campaign not found"}
    cap = clamp_discovery_cap(cap)
    queued = _stamp_discovery_metadata(
        eng,
        {"status": "queued", "message": RUNNING_MESSAGE, "cap": cap, "found": 0, "with_email": 0},
    )
    store.save_engagement(queued, tenant_id=tenant_id)

    if celery_worker_enabled() and spider is None:
        try:
            from engine.worker.celery_app import discover_campaign_people

            discover_campaign_people.delay(
                campaign_id=campaign_id,
                tenant_id=tenant_id,
                cap=cap,
            )
            return {
                "ok": True,
                "status": "queued",
                "message": RUNNING_MESSAGE,
                "campaign_id": campaign_id,
                "cap": cap,
            }
        except Exception:
            logger.exception("failed to enqueue people discovery; running inline")

    return run_campaign_people_discovery(
        store,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        cap=cap,
        spider=spider,
    )
