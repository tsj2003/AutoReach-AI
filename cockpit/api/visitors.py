"""5-Layer Website Visitor De-Anonymization, Identity Graph & Tracking Pixel API (`/api/visitors/*`).

Provides:
- `GET /api/visitors/wv.js`: Serves the lightweight 5-layer first-party tracking script exposing
  `window.AutoReachVisitors` and `window.GojiberryVisitors` (`grantConsent()`, `revokeConsent()`,
  `hasConsent()`, `identify()`, `track()`, `trackPageView()`).
- `POST /api/visitors/beacon` & `POST /api/visitors/collect`: Ingests visitor beacons across all 5 layers:
  1. Outbound Click & Email Token Stitching (`?_ar_vid=...`, `?_ar_pid=...`, `?_gb_cid=...`, `?utm_term=...`)
  2. Form / Cal.com / Chat / Newsletter Identity Stitching (`email` / `domain` from `identify()`)
  3. Cross-Session First-Party Cookie & Browser Fingerprint Identity Graph (`visitor_identity_graph`)
  4. Corporate rDNS + RDAP / ARIN / RIPE / APNIC WHOIS Lookup
  5. Referrer, UTM & High-Intent Behavioral Scoring (`/pricing` + `/demo` alerts, warmth score `0–100`)
- `POST /api/visitors/stitch-link`: Generates a signed `_ar_vid` outbound link for any prospect/contact.
- `GET /api/visitors/identity-graph`: Lists persistent nodes in `visitor_identity_graph`.
- `POST /api/visitors/simulate`: Simulates corporate or WFH/residential stitched visits.
- `GET /api/visitors/feed`: Lists de-anonymized visitors & intent warmth scores.
- `GET/PUT /api/visitors/config` & `GET /api/visitors/script-snippet`: Visitor tracking configuration & snippet.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from cockpit.api.deps import get_current_user, get_store
from engine.core.types import Prospect
from engine.services.company_intel_engine import crawl_and_fingerprint_company
from engine.services.email_finder_engine import find_and_verify_email
from engine.services.visitor_deanonymizer_engine import (
    encode_outbound_visitor_token,
    VisitorIdentityGraph,
    generate_stitched_outbound_url,
    generate_visitor_tracking_script_js,
    resolve_visitor_5_layer,
)
from engine.signals.catalog import compute_gojiberry_scores

router = APIRouter(prefix="/api/visitors", tags=["visitors"])

_VISITOR_CONFIG_KEY = "visitor_tracking:config"


class VisitorBeaconRequest(BaseModel):
    workspace_id: str = "default"
    uid: Optional[str] = None
    aid: Optional[str] = None
    visitor_id: Optional[str] = None
    cookie_visitor_id: Optional[str] = None
    ar_vid: Optional[str] = None
    ar_pid: Optional[str] = None
    gb_cid: Optional[str] = None
    ip_address: Optional[str] = None
    ip: Optional[str] = None
    ip_override: Optional[str] = None
    consent_granted: bool = True
    domain: Optional[str] = None
    domain_hint: Optional[str] = None
    company_domain_hint: Optional[str] = None
    company_hint: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    page_url: str = "https://app.autoreach.ai/pricing"
    page_path: str = "/pricing"
    page_title: str = "Pricing & Enterprise Plans"
    referrer: str = ""
    user_agent: str = ""
    language: str = ""
    screen_resolution: str = ""
    timezone: str = ""
    webgl_renderer: str = ""
    canvas_hash: str = ""
    platform: str = ""
    fingerprint_hash: str = ""
    utm_source: str = ""
    utm_term: str = ""
    duration_seconds: int = Field(default=45, ge=0, le=7200)
    time_on_page_seconds: int = Field(default=0, ge=0, le=7200)
    scroll_depth_pct: int = Field(default=0, ge=0, le=100)
    cta_clicks: int = Field(default=0, ge=0, le=100)
    pages_visited: Optional[List[str]] = None
    campaign_id: Optional[str] = None
    crawl_live: bool = False
    cascade_prospects: bool = True


class SimulateVisitorRequest(BaseModel):
    company_name: Optional[str] = None
    domain: Optional[str] = None
    ip_address: Optional[str] = None
    ip: Optional[str] = None
    ip_override: Optional[str] = None
    visitor_id: Optional[str] = None
    cookie_visitor_id: Optional[str] = None
    ar_vid: Optional[str] = None
    ar_pid: Optional[str] = None
    gb_cid: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    fingerprint_hash: Optional[str] = None
    user_agent: str = ""
    screen_resolution: str = ""
    timezone: str = ""
    webgl_renderer: str = ""
    consent_granted: bool = True
    page_url: Optional[str] = None
    page_path: str = "/pricing"
    pages_visited: Optional[List[str]] = None
    time_on_page_seconds: int = 65
    scroll_depth_pct: int = 80
    cta_clicks: int = 1
    campaign_id: Optional[str] = None
    crawl_live: bool = False


class VisitorConfigUpdate(BaseModel):
    enabled: bool = True
    target_campaign_id: Optional[str] = None
    auto_create_prospects: bool = True
    enrich_decision_makers: bool = True
    high_intent_paths: List[str] = Field(
        default_factory=lambda: ["/pricing", "/demo", "/enterprise", "/book", "/integrations", "/case-study"]
    )


class StitchLinkRequest(BaseModel):
    target_url: str
    prospect_id: str = ""
    contact_id: str = ""
    email: str = ""
    full_name: str = ""
    company_domain: str = ""
    company_name: str = ""
    campaign_id: str = ""


def _ensure_visitors_table(store: Any) -> None:
    with store._holder.engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS visitor_feed_store (k VARCHAR(64) PRIMARY KEY, v TEXT NOT NULL)"
            )
        )


def _load_visitor_feed(store: Any) -> List[Dict[str, Any]]:
    _ensure_visitors_table(store)
    with store._holder.engine.begin() as conn:
        row = conn.execute(text("SELECT v FROM visitor_feed_store WHERE k = 'visitors:feed'")).fetchone()
        if row and row[0]:
            try:
                parsed = json.loads(row[0])
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
    return []


def _save_visitor_feed(store: Any, items: List[Dict[str, Any]]) -> None:
    _ensure_visitors_table(store)
    with store._holder.engine.begin() as conn:
        conn.execute(
            text("DELETE FROM visitor_feed_store WHERE k = 'visitors:feed'")
        )
        conn.execute(
            text("INSERT INTO visitor_feed_store (k, v) VALUES ('visitors:feed', :v)"),
            {"v": json.dumps(items[:250])},
        )


def _load_config(store: Any) -> Dict[str, Any]:
    raw = store.get_kv(_VISITOR_CONFIG_KEY) if hasattr(store, "get_kv") else None
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {
        "enabled": True,
        "target_campaign_id": None,
        "auto_create_prospects": True,
        "enrich_decision_makers": True,
        "high_intent_paths": ["/pricing", "/demo", "/enterprise", "/book", "/integrations", "/case-study"],
        "pixel_id": "wv_autoreach_live",
        "layers_enabled": [
            "layer_1_outbound_token",
            "layer_2_form_identify",
            "layer_3_identity_graph",
            "layer_4_rdap_rdns",
            "layer_5_behavioral_utm",
        ],
    }


@router.get("/wv.js")
def get_visitor_pixel_script(request: Request) -> Response:
    """Serve the 5-Layer First-Party Website Visitor tracking & WFH identity-stitching script (`wv.js`)."""
    base_url = str(request.base_url).rstrip("/")
    collector_url = f"{base_url}/api/visitors/beacon"
    js_code = generate_visitor_tracking_script_js(collector_endpoint=collector_url)
    return Response(
        content=js_code,
        media_type="application/javascript; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=300",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/script-snippet")
def get_visitor_script_snippet(
    workspace_id: str = "default",
    user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    snippet = (
        f'<script defer src="/api/visitors/wv.js" '
        f'data-workspace="{workspace_id}" '
        f'data-endpoint="/api/visitors/beacon" '
        f'data-require-consent="false"></script>'
    )
    return {
        "workspace_id": workspace_id,
        "snippet": snippet,
        "consent_example": "window.AutoReachVisitors.identify({ email: 'founder@company.com' });",
    }


@router.get("/config")
def get_visitor_config(
    request: Request,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    cfg = _load_config(store)
    base_url = str(request.base_url).rstrip("/")
    script_url = f"{base_url}/api/visitors/wv.js"
    cfg["script_url"] = script_url
    cfg["embed_snippet"] = f'<script src="{script_url}" defer></script>'
    return cfg


@router.put("/config")
def update_visitor_config(
    req: VisitorConfigUpdate,
    request: Request,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    cfg = _load_config(store)
    cfg.update(req.model_dump())
    if hasattr(store, "set_kv"):
        store.set_kv(_VISITOR_CONFIG_KEY, json.dumps(cfg))
    base_url = str(request.base_url).rstrip("/")
    script_url = f"{base_url}/api/visitors/wv.js"
    cfg["script_url"] = script_url
    cfg["embed_snippet"] = f'<script src="{script_url}" defer></script>'
    return cfg


@router.post("/stitch-link")
def create_stitched_outbound_link(
    req: StitchLinkRequest,
    user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """Generate a signed `_ar_vid` outbound link so clicks from residential Wi-Fi / mobile / WFH
    are de-anonymized at 100% confidence when `wv.js` fires."""
    token = encode_outbound_visitor_token(
        prospect_id=req.prospect_id,
        contact_id=req.contact_id,
        email=req.email,
        full_name=req.full_name,
        company_domain=req.company_domain,
        company_name=req.company_name,
        campaign_id=req.campaign_id,
    )
    stitched_url = generate_stitched_outbound_url(
        req.target_url,
        prospect_id=req.prospect_id,
        contact_id=req.contact_id,
        email=req.email,
        full_name=req.full_name,
        company_domain=req.company_domain,
        company_name=req.company_name,
        campaign_id=req.campaign_id,
    )
    return {
        "ok": True,
        "original_url": req.target_url,
        "stitched_url": stitched_url,
        "_ar_vid": token,
        "ar_vid": token,
    }


@router.get("/identity-graph")
def get_visitor_identity_graph(
    limit: int = 50,
    user: Any = Depends(get_current_user),
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Inspect persistent nodes in the `visitor_identity_graph` table."""
    graph = VisitorIdentityGraph(store)
    nodes = graph.list_nodes(limit=limit)
    return {
        "ok": True,
        "count": len(nodes),
        "stats": {
            "known_identities": len(nodes),
            "wfh_stitched": sum(1 for n in nodes if n.get("resolution_layer") in (1, 2, 3)),
        },
        "nodes": nodes,
        "layers": [
            {"layer": 1, "id": "layer_1_outbound_token", "name": "Outbound Click & Email Token Stitching (_ar_vid)", "confidence": 1.0},
            {"layer": 2, "id": "layer_2_form_identify", "name": "Form / Cal.com / Chat Identity Stitching", "confidence": 0.98},
            {"layer": 3, "id": "layer_3_identity_graph", "name": "Cross-Session Cookie & WebGL/Canvas Fingerprint Graph", "confidence": 0.92},
            {"layer": 4, "id": "layer_4_rdap_rdns", "name": "Corporate rDNS + RDAP / ARIN / RIPE / APNIC WHOIS", "confidence": 0.85},
            {"layer": 5, "id": "layer_5_behavioral_utm", "name": "Referrer, UTM & High-Intent Behavioral Scoring", "confidence": 0.35},
        ],
    }


@router.post("/beacon")
@router.post("/collect")
def ingest_visitor_beacon(
    payload: VisitorBeaconRequest,
    request: Request,
    store: Any = Depends(get_store),
) -> Dict[str, Any]:
    """Ingest a website visitor beacon across all 5 De-Anonymization Layers, update `visitor_identity_graph`,
    and cascade resolved decision-makers into prospects."""
    client_ip = (
        payload.ip_override
        or payload.ip_address
        or payload.ip
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "127.0.0.1")
    )
    user_agent = payload.user_agent or request.headers.get("user-agent", "")
    eff_page_url = payload.url or payload.page_url or payload.page_path or "/pricing"
    eff_domain_hint = payload.domain or payload.domain_hint or payload.company_domain_hint or ""
    eff_time_sec = payload.time_on_page_seconds or payload.duration_seconds or 45

    res = resolve_visitor_5_layer(
        ip_address=client_ip,
        page_visited=eff_page_url,
        referrer=payload.referrer,
        visitor_id=payload.visitor_id or payload.cookie_visitor_id or "",
        ar_vid=payload.ar_vid or "",
        ar_pid=payload.ar_pid or "",
        gb_cid=payload.gb_cid or "",
        utm_source=payload.utm_source,
        utm_term=payload.utm_term,
        identified_email=payload.email or "",
        identified_domain=eff_domain_hint,
        identified_name=payload.full_name or "",
        user_agent=user_agent,
        screen_resolution=payload.screen_resolution,
        timezone_str=payload.timezone,
        language=payload.language,
        webgl_renderer=payload.webgl_renderer,
        canvas_hash=payload.canvas_hash,
        fingerprint_hash=payload.fingerprint_hash or "",
        time_on_page_seconds=eff_time_sec,
        scroll_depth_pct=payload.scroll_depth_pct,
        cta_clicks=payload.cta_clicks,
        pages_visited=payload.pages_visited,
        store=store,
        enrich_company=payload.crawl_live,
    )

    domain = res.company_domain
    company_name = res.company_name or payload.company_hint or (
        domain.split(".")[0].title() if domain else "Anonymous Visitor"
    )
    technologies: List[Dict[str, str]] = list(res.technologies)
    decision_makers: List[Dict[str, Any]] = [dm.as_dict() for dm in res.decision_makers]
    industry = "B2B Software"
    location = res.location or "United States"

    if payload.crawl_live and domain and res.is_corporate and not technologies:
        try:
            intel = crawl_and_fingerprint_company(domain, enrich_decision_maker_emails=False, timeout=3.5)
            company_name = intel.company_name or company_name
            industry = intel.industry or industry
            technologies = intel.technologies
            if not decision_makers:
                decision_makers = [asdict(dm) for dm in intel.decision_makers]
        except Exception:
            pass

    # No fabricated decision-makers. When the resolver identifies the company but
    # not the people (e.g. Layer 4 RDAP without a live crawl), decision_makers stays
    # empty — enable crawl_live to discover real leadership, or enrich later.

    cascaded_prospect_ids: List[str] = []
    if payload.cascade_prospects and res.is_corporate and domain:
        engagements = list(store.list_engagements())
        target_campaign = payload.campaign_id or (engagements[0].id if engagements else "default")
        for dm in decision_makers[:2]:
            first = (dm.get("first_name") or "").strip()
            last = (dm.get("last_name") or "").strip()
            dm_email = dm.get("email") or res.person_email
            if not first and not dm_email:
                # No real identity for this decision-maker — don't invent one.
                continue
            if not dm_email:
                email_res = find_and_verify_email(
                    first_name=first,
                    last_name=last,
                    domain=domain,
                    company_name=company_name,
                    enable_osint_harvest=False,
                    enable_smtp_probe=False,
                )
                dm_email = email_res.best_email
                alt_emails = email_res.alternate_emails
            else:
                alt_emails = []

            pid = res.prospect_id or f"pros_{uuid.uuid4().hex[:10]}"
            sig_obj = {
                "id": f"sig_{uuid.uuid4().hex[:8]}",
                "signal_type": "WEBSITE_VISITOR",
                "name": "Website visitors",
                "intent_points": 3,
                "keyword": f"Visited {payload.page_path}",
                "source_url": eff_page_url,
                "resolution_layer": res.resolution_layer,
                "resolution_method": res.resolution_method,
                "is_wfh_stitched": res.is_wfh_stitched,
                "intent_warmth_score": res.intent_warmth_score,
                "high_intent_alert": res.high_intent_alert,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            scores = compute_gojiberry_scores(
                lead_score=float(max(86, res.intent_warmth_score)),
                fit_status="good_fit",
                title=dm.get("title", "VP of Growth"),
                company_name=company_name,
                signals=[sig_obj],
                intent_type="WEBSITE_VISITOR",
            )
            notes = {
                "domain": domain,
                "company_domain": domain,
                "industry": industry,
                "location": location,
                "fit": "good_fit",
                "intent": scores["intent"],
                "intent_type": "WEBSITE_VISITOR",
                "intent_keyword": f"Visited {payload.page_path}",
                "resolution_layer": res.resolution_layer,
                "resolution_method": res.resolution_method,
                "is_wfh_stitched": res.is_wfh_stitched,
                "intent_warmth_score": res.intent_warmth_score,
                "high_intent_alert": res.high_intent_alert,
                "signals": [sig_obj],
                "email_2": alt_emails[0] if len(alt_emails) >= 1 else "",
                "email_3": alt_emails[1] if len(alt_emails) >= 2 else "",
            }
            if target_campaign != "default":
                p = Prospect(
                    id=pid,
                    engagement_id=target_campaign,
                    email=dm_email,
                    full_name=dm.get("full_name") or f"{first} {last}".strip(),
                    company=company_name,
                    title=dm.get("title", "VP of Growth"),
                    research=notes,
                )
                store.save_prospect(p)
            cascaded_prospect_ids.append(pid)

    norm_method = {
        "layer_1_outbound_token": "layer1_outbound_click_token",
        "layer_2_form_identify": "layer2_form_email_stitch",
        "layer_3_identity_graph": "layer3_fingerprint_identity_graph",
        "layer_4_rdap_rdns": "layer4_corporate_rdap_whois",
        "layer_5_behavioral_utm": "layer5_utm_referrer_behavioral",
    }.get(res.resolution_method, res.resolution_method)
    resolved_pid = res.prospect_id or (cascaded_prospect_ids[0] if cascaded_prospect_ids else "")
    prospect_obj = None
    if resolved_pid:
        p_rec = store.get_prospect(resolved_pid)
        if p_rec:
            prospect_obj = {"id": p_rec.id, "email": p_rec.email, "full_name": p_rec.full_name, "company": p_rec.company}
    if not prospect_obj and res.person_email:
        prospect_obj = {"id": resolved_pid, "email": res.person_email, "full_name": res.person_name or "Decision Maker", "company": company_name}

    event_record = {
        "id": f"vse_{uuid.uuid4().hex[:10]}",
        "visitor_id": res.visitor_id,
        "fingerprint_hash": res.fingerprint_hash,
        "ip_address": client_ip,
        "identified": bool(res.is_corporate or res.resolution_layer in (1, 2, 3, 4)),
        "is_corporate": res.is_corporate,
        "is_wfh_stitched": res.is_wfh_stitched,
        "resolution_layer": res.resolution_layer,
        "resolution_method": norm_method,
        "warmth_score": res.intent_warmth_score,
        "prospect": prospect_obj,
        "classification": res.classification,
        "confidence": res.confidence,
        "company_name": company_name,
        "company_domain": domain,
        "domain": domain,
        "prospect_id": res.prospect_id or (cascaded_prospect_ids[0] if cascaded_prospect_ids else ""),
        "person_email": res.person_email,
        "person_name": res.person_name,
        "reverse_dns": res.reverse_dns,
        "network_name": res.network_name,
        "industry": industry,
        "location": location,
        "page_url": eff_page_url,
        "page_path": payload.page_path,
        "page_title": payload.page_title,
        "pages_visited": res.pages_visited,
        "duration_seconds": eff_time_sec,
        "time_on_page_seconds": res.time_on_page_seconds,
        "scroll_depth_pct": res.scroll_depth_pct,
        "cta_clicks": res.cta_clicks,
        "intent_warmth_score": res.intent_warmth_score,
        "high_intent_alert": res.high_intent_alert,
        "technologies": technologies,
        "decision_makers": decision_makers,
        "cascaded_prospect_ids": cascaded_prospect_ids,
        "visited_at": datetime.now(timezone.utc).isoformat(),
    }

    feed = _load_visitor_feed(store)
    feed.insert(0, event_record)
    _save_visitor_feed(store, feed)

    return {
        "status": "resolved" if res.is_corporate else "recorded_behavioral",
        "visitor": event_record,
        **event_record,
    }


@router.get("/feed")
def get_visitor_feed(
    corporate_only: bool = False,
    limit: int = 50,
    workspace_id: str = "default",
    store: Any = Depends(get_store),
    user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    feed = _load_visitor_feed(store)
    if corporate_only:
        feed = [item for item in feed if item.get("is_corporate")]
    snippet = (
        f'<script defer src="/api/visitors/wv.js?uid={workspace_id}&aid=default" '
        f'data-workspace="{workspace_id}" '
        f'data-endpoint="/api/visitors/beacon" '
        f'data-require-consent="false"></script>'
    )
    return {
        "total": len(feed[:limit]),
        "corporate_count": sum(1 for item in feed if item.get("is_corporate")),
        "wfh_stitched_count": sum(1 for item in feed if item.get("is_wfh_stitched")),
        "high_intent_count": sum(1 for item in feed if item.get("high_intent_alert")),
        "stats": {
            "layer_breakdown": {
                "layer_1_outbound_token": sum(1 for item in feed if item.get("resolution_layer") == 1),
                "layer_2_form_email": sum(1 for item in feed if item.get("resolution_layer") == 2),
                "layer_3_fingerprint_graph": sum(1 for item in feed if item.get("resolution_layer") == 3),
                "layer_4_rdap_rdns": sum(1 for item in feed if item.get("resolution_layer") == 4),
                "layer_5_behavioral_utm": sum(1 for item in feed if item.get("resolution_layer") == 5),
            }
        },
        "items": feed[:limit],
        "visitors": feed[:limit],
        "snippet": snippet,
    }


@router.post("/simulate")
def simulate_corporate_visitor(
    payload: SimulateVisitorRequest,
    request: Request,
    store: Any = Depends(get_store),
    user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run a visitor-resolution test against a REAL domain/IP through the live 5-layer
    pipeline. No fabricated companies or decision-makers — provide a domain (or IP,
    or an identity token) and the resolver returns whatever it can actually verify.
    Enable `crawl_live` to discover real leadership for the resolved company."""
    has_identity = bool(payload.ar_vid or payload.ar_pid or payload.gb_cid or payload.fingerprint_hash or payload.email)
    domain = (payload.domain or "").strip().lower()
    ip = (payload.ip_address or payload.ip or payload.ip_override or "").strip()
    if not domain and not ip and not has_identity:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="Provide a domain, an IP address, or an identity token (ar_vid/email) to resolve a real visitor.",
        )

    eff_path = payload.page_path or "/pricing"
    eff_url = payload.page_url or f"https://app.autoreach.ai{eff_path}"

    beacon = VisitorBeaconRequest(
        visitor_id=payload.visitor_id,
        ar_vid=payload.ar_vid,
        ar_pid=payload.ar_pid,
        gb_cid=payload.gb_cid,
        ip_address=ip or None,
        domain_hint=domain or None,
        company_hint=payload.company_name or None,
        email=payload.email,
        full_name=payload.full_name,
        fingerprint_hash=payload.fingerprint_hash or "",
        user_agent=payload.user_agent,
        screen_resolution=payload.screen_resolution,
        timezone=payload.timezone,
        webgl_renderer=payload.webgl_renderer,
        page_path=eff_path,
        page_url=eff_url,
        page_title="Pricing & Plans",
        pages_visited=payload.pages_visited or [eff_path],
        time_on_page_seconds=payload.time_on_page_seconds,
        scroll_depth_pct=payload.scroll_depth_pct,
        cta_clicks=payload.cta_clicks,
        campaign_id=payload.campaign_id,
        crawl_live=payload.crawl_live,
        cascade_prospects=True,
    )
    return ingest_visitor_beacon(beacon, request, store)
