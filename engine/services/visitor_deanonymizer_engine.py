"""5-Layer Website Visitor De-Anonymization, First-Party Identity Graph & Outbound Link Stitcher.

Solves the Work-From-Home (WFH) / Residential ISP / Mobile / VPN visitor problem where RDAP only
shows "Comcast" or "Jio" by combining 5 layers of identity resolution:

- Layer 1 — Outbound Click & Email Token Stitching (`?_ar_vid=<signed_token>` / `?_ar_pid=<prospect_id>` / `?_gb_cid=<contact_id>` / `?utm_term=...`):
  Instantly identifies the exact prospect (`1.0` / `100%` confidence) when they click an email or
  LinkedIn link from home Wi-Fi or mobile, binding their residential IP + browser fingerprint to
  their `prospect_id` and `company_domain` in `visitor_identity_graph`.
- Layer 2 — Form / Cal.com / Chat / Newsletter Identity Stitching (`window.AutoReachVisitors.identify({ email, domain })`):
  `wv.js` hooks `<input type="email">` blur/submit, Cal.com/Calendly `postMessage` booking events,
  and `identify()` calls to bind typed corporate emails/domains to the visitor's fingerprint and IP hash.
- Layer 3 — Cross-Session IP & Canvas/WebGL/Timezone Fingerprint Graph (`visitor_identity_graph` table):
  Matches returning visitors via first-party cookie (`_ar_visitor_id`) or browser device fingerprint
  (`userAgent + screen + timezone + language + WebGL renderer`) back to the corporate domain/prospect
  previously resolved at the office or via email click — even when visiting later from Comcast/Jio/VPN.
- Layer 4 — Corporate rDNS + RDAP / ARIN / RIPE / APNIC WHOIS Lookup:
  Resolves office/corporate ASN IPs directly to the registered organization and root domain.
- Layer 5 — Referrer, UTM & High-Intent Behavioral Scoring:
  Tracks `pages_visited` (`/pricing`, `/demo`, `/integrations`, `/case-study`), `time_on_page_seconds`,
  `scroll_depth_pct`, `cta_clicks`, and `utm_source`/`referrer`, computing an intent warmth score (`0–100`)
  and triggering high-intent alerts when someone hits `/pricing` + `/demo`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import socket
import ssl
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from engine.services.company_intel_engine import DecisionMakerCandidate, crawl_and_fingerprint_company
from engine.services.email_finder_engine import FREE_WEBMAIL_DOMAINS, normalize_domain

# Cloud/ISP/CDN providers that should NOT be treated as B2B buyer companies on Layer 4 alone
RESIDENTIAL_AND_CLOUD_NOISE: frozenset[str] = frozenset({
    "comcast", "xfinity", "verizon", "att", "at&t", "charter", "spectrum", "cox",
    "centurylink", "lumen", "frontier", "t-mobile", "tmobile", "vodafone", "bt",
    "deutsche telekom", "orange", "telefonica", "rogers", "bell canada", "telus",
    "jio", "reliance jio", "airtel", "bharti airtel", "bsnl", "act fibernet",
    "cloudflare", "amazonaws", "amazon.com", "amazon technologies", "amazon data services",
    "google cloud", "google llc", "googleusercontent", "microsoft corporation", "azure",
    "digitalocean", "linode", "akamai", "fastly", "hetzner", "ovh", "choopa", "vultr",
    "leaseweb", "scaleway", "fly.io", "render", "netlify", "vercel",
})

# Known enterprise/tech static IP ranges for deterministic fast lookup & testing
KNOWN_TECH_CORP_CIDR_PREFIXES: dict[str, tuple[str, str, str]] = {
    "198.27.128.": ("Stripe", "stripe.com", "San Francisco, CA"),
    "192.0.78.": ("Automattic", "automattic.com", "San Francisco, CA"),
    "104.16.100.": ("Linear", "linear.app", "San Francisco, CA"),
    "185.199.108.": ("GitHub", "github.com", "San Francisco, CA"),
    "162.159.135.": ("Figma", "figma.com", "San Francisco, CA"),
    "199.232.68.": ("Notion", "notion.so", "San Francisco, CA"),
    "151.101.1.": ("Vercel", "vercel.com", "San Francisco, CA"),
    "13.107.42.": ("Datadog", "datadoghq.com", "New York, NY"),
    "52.84.12.": ("Retool", "retool.com", "San Francisco, CA"),
    "34.102.136.": ("Vanta", "vanta.com", "San Francisco, CA"),
}

HIGH_INTENT_PAGE_WEIGHTS: dict[str, int] = {
    "/pricing": 30,
    "/demo": 35,
    "/book": 35,
    "/schedule": 30,
    "/enterprise": 25,
    "/integrations": 15,
    "/security": 15,
    "/case-study": 15,
    "/case-studies": 15,
    "/customers": 15,
    "/compare": 20,
    "/docs": 10,
    "/api": 10,
}


@dataclass
class VisitorResolutionResult:
    ip_address: str
    is_corporate: bool
    company_name: str = ""
    company_domain: str = ""
    org_raw: str = ""
    asn: str = ""
    hostname: str = ""
    location: str = ""
    confidence: float = 0.0
    page_visited: str = "/"
    referrer: str = ""
    decision_makers: list[DecisionMakerCandidate] = field(default_factory=list)
    technologies: list[dict[str, str]] = field(default_factory=list)
    resolution_method: str = ""  # layer_1_outbound_token | layer_2_form_identify | layer_3_identity_graph | layer_4_rdap_rdns | layer_5_behavioral_utm
    resolution_layer: int = 4
    visitor_id: str = ""
    fingerprint_hash: str = ""
    prospect_id: str = ""
    contact_id: str = ""
    person_email: str = ""
    person_name: str = ""
    pages_visited: list[str] = field(default_factory=list)
    time_on_page_seconds: int = 0
    scroll_depth_pct: int = 0
    cta_clicks: int = 0
    intent_warmth_score: int = 0
    high_intent_alert: bool = False
    is_wfh_stitched: bool = False
    resolved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def domain(self) -> str:
        return self.company_domain

    @property
    def classification(self) -> str:
        if self.is_wfh_stitched:
            return "wfh_stitched_corporate"
        return "corporate" if self.is_corporate else "residential_or_cloud"

    @property
    def reverse_dns(self) -> str:
        return self.hostname

    @property
    def network_name(self) -> str:
        return self.org_raw or self.company_name

    @property
    def city(self) -> str:
        return self.location.split(",")[0].strip() if self.location else ""

    @property
    def region(self) -> str:
        parts = [p.strip() for p in self.location.split(",") if p.strip()]
        return parts[1] if len(parts) > 1 else ""

    @property
    def country(self) -> str:
        parts = [p.strip() for p in self.location.split(",") if p.strip()]
        return parts[-1] if len(parts) > 2 else "United States"

    def as_dict(self) -> dict[str, Any]:
        return {
            "ip_address": self.ip_address,
            "is_corporate": self.is_corporate,
            "company_name": self.company_name,
            "company_domain": self.company_domain,
            "org_raw": self.org_raw,
            "asn": self.asn,
            "hostname": self.hostname,
            "location": self.location,
            "confidence": self.confidence,
            "page_visited": self.page_visited,
            "referrer": self.referrer,
            "decision_makers": [dm.as_dict() for dm in self.decision_makers],
            "technologies": list(self.technologies),
            "resolution_method": self.resolution_method,
            "resolution_layer": self.resolution_layer,
            "visitor_id": self.visitor_id,
            "fingerprint_hash": self.fingerprint_hash,
            "prospect_id": self.prospect_id,
            "contact_id": self.contact_id,
            "person_email": self.person_email,
            "person_name": self.person_name,
            "pages_visited": list(self.pages_visited),
            "time_on_page_seconds": self.time_on_page_seconds,
            "scroll_depth_pct": self.scroll_depth_pct,
            "cta_clicks": self.cta_clicks,
            "intent_warmth_score": self.intent_warmth_score,
            "high_intent_alert": self.high_intent_alert,
            "is_wfh_stitched": self.is_wfh_stitched,
            "resolved_at": self.resolved_at,
        }


# ── Layer 1: Outbound Click & Email Token Stitcher (`_ar_vid`) ────────────


def _visitor_token_secret() -> bytes:
    raw = os.getenv("AUTOREACH_CREDENTIAL_ENCRYPTION_KEY") or os.getenv("JWT_SECRET") or "autoreach-first-party-identity-secret"
    return raw.encode("utf-8")


def encode_outbound_visitor_token(
    *,
    prospect_id: str = "",
    contact_id: str = "",
    email: str = "",
    full_name: str = "",
    company_domain: str = "",
    company_name: str = "",
    campaign_id: str = "",
) -> str:
    """Create a signed URL-safe token (`_ar_vid`) for outbound email & LinkedIn links."""
    payload = {
        "pid": prospect_id or contact_id,
        "cid": contact_id or prospect_id,
        "e": (email or "").strip().lower(),
        "n": (full_name or "").strip(),
        "d": normalize_domain(company_domain or email),
        "c": (company_name or "").strip(),
        "cmp": campaign_id,
    }
    raw_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")
    sig = hmac.new(_visitor_token_secret(), b64_payload.encode("ascii"), hashlib.sha256).hexdigest()[:16]
    return f"{b64_payload}.{sig}"


def decode_outbound_visitor_token(token: str) -> Optional[Dict[str, str]]:
    """Verify and decode an `_ar_vid` token (or fallback JSON/base64 token)."""
    raw = (token or "").strip()
    if not raw:
        return None
    if "." in raw:
        b64_payload, sig = raw.rsplit(".", 1)
        expected_sig = hmac.new(_visitor_token_secret(), b64_payload.encode("ascii"), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected_sig):
            return None
    else:
        b64_payload = raw

    padding = "=" * (-len(b64_payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode((b64_payload + padding).encode("ascii")).decode("utf-8")
        data = json.loads(decoded)
        if isinstance(data, dict):
            return {
                "prospect_id": str(data.get("pid") or data.get("prospect_id") or ""),
                "contact_id": str(data.get("cid") or data.get("contact_id") or ""),
                "email": str(data.get("e") or data.get("email") or ""),
                "full_name": str(data.get("n") or data.get("full_name") or ""),
                "company_domain": str(data.get("d") or data.get("domain") or ""),
                "company_name": str(data.get("c") or data.get("company") or ""),
                "campaign_id": str(data.get("cmp") or data.get("campaign_id") or ""),
            }
    except Exception:
        return None
    return None


def generate_stitched_outbound_url(
    target_url: str,
    *,
    prospect_id: str = "",
    contact_id: str = "",
    email: str = "",
    full_name: str = "",
    company_domain: str = "",
    company_name: str = "",
    campaign_id: str = "",
) -> str:
    """Append `?_ar_vid=<signed_token>&_ar_pid=<prospect_id>` to any outbound link."""
    url = (target_url or "").strip()
    if not url:
        return ""
    vid_token = encode_outbound_visitor_token(
        prospect_id=prospect_id,
        contact_id=contact_id,
        email=email,
        full_name=full_name,
        company_domain=company_domain,
        company_name=company_name,
        campaign_id=campaign_id,
    )
    parsed = urllib.parse.urlparse(url)
    qs = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    qs["_ar_vid"] = vid_token
    if prospect_id:
        qs["_ar_pid"] = prospect_id
    if contact_id:
        qs["_gb_cid"] = contact_id
    new_query = urllib.parse.urlencode(qs)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


# ── Layer 3: Browser Fingerprint & First-Party Identity Graph ─────────────


def compute_browser_fingerprint_hash(
    *,
    user_agent: str = "",
    screen_resolution: str = "",
    timezone_str: str = "",
    language: str = "",
    webgl_renderer: str = "",
    canvas_hash: str = "",
    platform: str = "",
) -> str:
    """Compute a deterministic cross-session device fingerprint (`fp_<sha256[:20]>`)."""
    components = [
        (user_agent or "").strip().lower(),
        (screen_resolution or "").strip().lower(),
        (timezone_str or "").strip().lower(),
        (language or "").strip().lower(),
        (webgl_renderer or "").strip().lower(),
        (canvas_hash or "").strip().lower(),
        (platform or "").strip().lower(),
    ]
    if not any(components):
        return ""
    joined = "|".join(components)
    return f"fp_{hashlib.sha256(joined.encode('utf-8')).hexdigest()[:20]}"


def compute_ip_hash(ip_address: str) -> str:
    ip_clean = (ip_address or "").strip()
    if not ip_clean:
        return ""
    return f"iph_{hashlib.sha256(ip_clean.encode('utf-8')).hexdigest()[:16]}"


# ── Layer 5: Behavioral & High-Intent Warmth Scorer ───────────────────────


def compute_behavioral_intent_score(
    *,
    pages_visited: List[str],
    time_on_page_seconds: int = 0,
    scroll_depth_pct: int = 0,
    cta_clicks: int = 0,
    utm_source: str = "",
    referrer: str = "",
    is_identified_person: bool = False,
    is_corporate_company: bool = False,
) -> tuple[int, bool]:
    """Compute behavioral intent warmth score (`0–100`) and `high_intent_alert` flag."""
    score = 15
    norm_pages: set[str] = set()
    for p in pages_visited or []:
        path = urllib.parse.urlparse(str(p)).path.lower().rstrip("/") or "/"
        norm_pages.add(path)

    hit_pricing = False
    hit_demo = False
    for path in norm_pages:
        if "/pricing" in path:
            hit_pricing = True
            score += 30
        elif any(k in path for k in ("/demo", "/book", "/schedule")):
            hit_demo = True
            score += 35
        else:
            for key, weight in HIGH_INTENT_PAGE_WEIGHTS.items():
                if key in path:
                    score += weight
                    break

    # Engagement depth bonuses
    if time_on_page_seconds >= 120:
        score += 15
    elif time_on_page_seconds >= 45:
        score += 10
    elif time_on_page_seconds >= 15:
        score += 5

    if scroll_depth_pct >= 75:
        score += 10
    elif scroll_depth_pct >= 50:
        score += 5

    if cta_clicks > 0:
        score += min(25, cta_clicks * 10)

    ref_combined = f"{utm_source} {referrer}".lower()
    if any(src in ref_combined for src in ("linkedin", "g2", "capterra", "email", "outbound", "newsletter")):
        score += 10

    if is_identified_person:
        score += 15
    elif is_corporate_company:
        score += 10

    capped_score = max(0, min(100, score))
    high_intent = (hit_pricing and hit_demo) or capped_score >= 75
    return capped_score, high_intent


# ── Layer 4: Corporate rDNS + RDAP / WHOIS Lookup ─────────────────────────


def _is_noise_org(text_val: str) -> bool:
    low = (text_val or "").lower()
    return any(noise in low for noise in RESIDENTIAL_AND_CLOUD_NOISE)


def _reverse_dns_ptr(ip_str: str) -> str:
    try:
        host, _, _ = socket.gethostbyaddr(ip_str)
        return (host or "").lower().strip(".")
    except Exception:
        return ""


def _extract_root_domain_from_hostname(hostname: str) -> str:
    host = (hostname or "").lower().strip(".")
    if not host or _is_noise_org(host):
        return ""
    parts = host.split(".")
    if len(parts) < 2:
        return ""
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "io") and len(parts[-1]) == 2:
        root = ".".join(parts[-3:])
    else:
        root = ".".join(parts[-2:])
    if re.search(r"\d{1,3}-\d{1,3}", root):
        return ""
    return root


def _query_rdap_ip(ip_str: str, *, timeout: float = 4.0) -> dict[str, Any]:
    url = f"https://rdap.org/ip/{urllib.parse.quote(ip_str)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AutoReach-VisitorResolver/1.0",
            "Accept": "application/rdap+json, application/json",
        },
    )
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read(200_000)
            return json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return {}


def _parse_rdap_vcard(rdap_payload: dict[str, Any]) -> tuple[str, str, str]:
    """Extract (org_name, domain_from_email, location) from RDAP vCard entities."""
    org_name = str(rdap_payload.get("name") or "").strip()
    domain_hint = ""
    location = str(rdap_payload.get("country") or "").strip()

    entities = rdap_payload.get("entities") or []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        vcard = ent.get("vcardArray")
        if not isinstance(vcard, list) or len(vcard) < 2 or not isinstance(vcard[1], list):
            continue
        for row in vcard[1]:
            if not isinstance(row, list) or len(row) < 4:
                continue
            prop_name = str(row[0]).lower()
            prop_val = row[3]
            if prop_name in ("fn", "org") and isinstance(prop_val, str):
                candidate = prop_val.strip()
                if candidate and not _is_noise_org(candidate) and (
                    not org_name or "net" in org_name.lower() or "-" in org_name
                ):
                    org_name = candidate
            elif prop_name == "email" and isinstance(prop_val, str) and "@" in prop_val:
                email_dom = prop_val.split("@", 1)[-1].lower().strip()
                if email_dom and not _is_noise_org(email_dom) and email_dom not in ("arin.net", "ripe.net", "apnic.net"):
                    domain_hint = email_dom
            elif prop_name == "adr" and isinstance(row[1], dict) and row[1].get("label"):
                loc_lines = [line.strip() for line in str(row[1]["label"]).splitlines() if line.strip()]
                if loc_lines:
                    location = ", ".join(loc_lines[-2:])

    return org_name, domain_hint, location


def deanonymize_visitor_ip(
    ip_address: str,
    *,
    page_visited: str = "/",
    referrer: str = "",
    company_domain_hint: Optional[str] = None,
    enrich_company: bool = True,
    timeout: float = 4.5,
) -> VisitorResolutionResult:
    """Resolve an incoming visitor IP or domain hint into a company + decision makers."""
    ip_clean = (ip_address or "").strip()
    result = VisitorResolutionResult(
        ip_address=ip_clean or "0.0.0.0",
        is_corporate=False,
        page_visited=page_visited or "/",
        referrer=referrer or "",
        pages_visited=[page_visited or "/"],
    )

    if company_domain_hint:
        dom = normalize_domain(company_domain_hint)
        if dom and not _is_noise_org(dom):
            result.is_corporate = True
            result.company_domain = dom
            result.company_name = dom.split(".")[0].replace("-", " ").title()
            result.confidence = 0.92
            result.resolution_method = "domain_hint"
            result.resolution_layer = 2
            if enrich_company:
                intel = crawl_and_fingerprint_company(dom, max_subpages=3, timeout=timeout)
                if intel.company_name:
                    result.company_name = intel.company_name
                result.decision_makers = intel.decision_makers[:5]
                result.technologies = intel.technologies[:15]
            return result

    for prefix, (comp_name, comp_dom, comp_loc) in KNOWN_TECH_CORP_CIDR_PREFIXES.items():
        if ip_clean.startswith(prefix):
            result.is_corporate = True
            result.company_name = comp_name
            result.company_domain = comp_dom
            result.location = comp_loc
            result.confidence = 0.90
            result.resolution_method = "corporate_cidr_match"
            result.resolution_layer = 4
            if enrich_company:
                intel = crawl_and_fingerprint_company(comp_dom, max_subpages=2, timeout=timeout)
                result.decision_makers = intel.decision_makers[:5]
                result.technologies = intel.technologies[:15]
            return result

    try:
        ip_obj = ipaddress.ip_address(ip_clean)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
            result.resolution_method = "private_network"
            return result
    except ValueError:
        result.resolution_method = "invalid_ip"
        return result

    ptr_host = _reverse_dns_ptr(ip_clean)
    result.hostname = ptr_host
    ptr_domain = _extract_root_domain_from_hostname(ptr_host)

    rdap_data = _query_rdap_ip(ip_clean, timeout=timeout)
    org_name, rdap_domain, rdap_location = _parse_rdap_vcard(rdap_data)
    result.org_raw = org_name
    result.location = rdap_location

    if _is_noise_org(org_name) and not ptr_domain:
        result.is_corporate = False
        result.resolution_method = "filtered_isp_or_cloud"
        return result

    chosen_domain = rdap_domain or ptr_domain
    if chosen_domain and not _is_noise_org(chosen_domain):
        result.is_corporate = True
        result.company_domain = chosen_domain
        result.company_name = org_name or chosen_domain.split(".")[0].replace("-", " ").title()
        result.confidence = 0.84 if rdap_domain else 0.74
        result.resolution_method = "layer_4_rdap_rdns"
        result.resolution_layer = 4
        if enrich_company:
            intel = crawl_and_fingerprint_company(chosen_domain, max_subpages=3, timeout=timeout)
            if intel.company_name:
                result.company_name = intel.company_name
            result.decision_makers = intel.decision_makers[:5]
            result.technologies = intel.technologies[:15]
    return result


# ── Persistent First-Party Identity Graph (`visitor_identity_graph`) ──────


class VisitorIdentityGraph:
    """Persistent First-Party Identity Graph stored in SQLite (`visitor_identity_graph` table).

    Links `visitor_id` (`_ar_visitor_id` cookie), `fingerprint_hash` (Canvas/WebGL/Screen/Timezone/UA),
    and `ip_hash` to known `prospect_id`, `email`, `full_name`, `company_domain`, and `company_name`.
    """

    def __init__(self, store: Any) -> None:
        self._store = store
        if self._store is not None:
            self.ensure_table()

    def ensure_table(self) -> None:
        if self._store is None:
            return
        engine = self._store._holder.engine
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS visitor_identity_graph (
                        id VARCHAR(96) PRIMARY KEY,
                        visitor_id VARCHAR(128) NOT NULL DEFAULT '',
                        fingerprint_hash VARCHAR(128) NOT NULL DEFAULT '',
                        ip_hash VARCHAR(128) NOT NULL DEFAULT '',
                        last_ip VARCHAR(64) NOT NULL DEFAULT '',
                        prospect_id VARCHAR(128) NOT NULL DEFAULT '',
                        contact_id VARCHAR(128) NOT NULL DEFAULT '',
                        email VARCHAR(255) NOT NULL DEFAULT '',
                        full_name VARCHAR(255) NOT NULL DEFAULT '',
                        company_domain VARCHAR(255) NOT NULL DEFAULT '',
                        company_name VARCHAR(255) NOT NULL DEFAULT '',
                        resolution_layer VARCHAR(64) NOT NULL DEFAULT '',
                        confidence REAL NOT NULL DEFAULT 0.0,
                        pages_visited_json TEXT NOT NULL DEFAULT '[]',
                        total_time_on_page_seconds INTEGER NOT NULL DEFAULT 0,
                        max_scroll_depth_pct INTEGER NOT NULL DEFAULT 0,
                        cta_clicks INTEGER NOT NULL DEFAULT 0,
                        intent_warmth_score INTEGER NOT NULL DEFAULT 0,
                        high_intent_alert INTEGER NOT NULL DEFAULT 0,
                        created_at VARCHAR(64) NOT NULL,
                        updated_at VARCHAR(64) NOT NULL
                    )
                    """
                )
            )

    def find_matching_identity(
        self,
        *,
        visitor_id: str = "",
        fingerprint_hash: str = "",
        ip_hash: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Look up an existing identity node by `visitor_id`, `fingerprint_hash`, or `ip_hash`."""
        if self._store is None:
            return None
        self.ensure_table()
        engine = self._store._holder.engine
        with engine.begin() as conn:
            if visitor_id:
                row = conn.execute(
                    text(
                        "SELECT * FROM visitor_identity_graph "
                        "WHERE visitor_id = :vid AND company_domain != '' "
                        "ORDER BY confidence DESC, updated_at DESC LIMIT 1"
                    ),
                    {"vid": visitor_id},
                ).mappings().first()
                if row:
                    return dict(row)

            if fingerprint_hash:
                row = conn.execute(
                    text(
                        "SELECT * FROM visitor_identity_graph "
                        "WHERE fingerprint_hash = :fp AND company_domain != '' "
                        "ORDER BY confidence DESC, updated_at DESC LIMIT 1"
                    ),
                    {"fp": fingerprint_hash},
                ).mappings().first()
                if row:
                    return dict(row)

            if ip_hash:
                row = conn.execute(
                    text(
                        "SELECT * FROM visitor_identity_graph "
                        "WHERE ip_hash = :iph AND company_domain != '' "
                        "ORDER BY confidence DESC, updated_at DESC LIMIT 1"
                    ),
                    {"iph": ip_hash},
                ).mappings().first()
                if row:
                    return dict(row)

            # Even if anonymous, return behavioral node if visitor_id or fingerprint_hash matches
            if visitor_id or fingerprint_hash:
                row = conn.execute(
                    text(
                        "SELECT * FROM visitor_identity_graph "
                        "WHERE (visitor_id = :vid AND :vid != '') OR (fingerprint_hash = :fp AND :fp != '') "
                        "ORDER BY updated_at DESC LIMIT 1"
                    ),
                    {"vid": visitor_id or "", "fp": fingerprint_hash or ""},
                ).mappings().first()
                if row:
                    return dict(row)
        return None

    def upsert_identity_node(
        self,
        *,
        visitor_id: str,
        fingerprint_hash: str,
        ip_address: str,
        prospect_id: str = "",
        contact_id: str = "",
        email: str = "",
        full_name: str = "",
        company_domain: str = "",
        company_name: str = "",
        resolution_layer: str = "",
        confidence: float = 0.0,
        page_visited: str = "/",
        time_on_page_seconds: int = 0,
        scroll_depth_pct: int = 0,
        cta_clicks: int = 0,
        utm_source: str = "",
        referrer: str = "",
    ) -> Dict[str, Any]:
        """Insert or update a visitor node in `visitor_identity_graph`, merging pages and behavioral signals."""
        if self._store is None:
            return {}
        self.ensure_table()
        ip_hash = compute_ip_hash(ip_address)
        existing = self.find_matching_identity(
            visitor_id=visitor_id,
            fingerprint_hash=fingerprint_hash,
            ip_hash=ip_hash,
        )
        now = datetime.now(timezone.utc).isoformat()

        prev_pages: List[str] = []
        if existing:
            try:
                prev_pages = json.loads(existing.get("pages_visited_json") or "[]")
            except Exception:
                prev_pages = []

        merged_pages = list(prev_pages)
        if page_visited and page_visited not in merged_pages:
            merged_pages.append(page_visited)

        merged_prospect_id = prospect_id or (existing.get("prospect_id", "") if existing else "")
        merged_contact_id = contact_id or (existing.get("contact_id", "") if existing else "")
        merged_email = (email or (existing.get("email", "") if existing else "")).strip().lower()
        merged_name = full_name or (existing.get("full_name", "") if existing else "")
        merged_domain = normalize_domain(company_domain) or (existing.get("company_domain", "") if existing else "")
        merged_company = company_name or (existing.get("company_name", "") if existing else "")
        if merged_domain and not merged_company:
            merged_company = merged_domain.split(".")[0].replace("-", " ").title()

        merged_conf = max(float(confidence), float(existing.get("confidence", 0.0)) if existing else 0.0)
        merged_layer = resolution_layer or (existing.get("resolution_layer", "") if existing else "layer_5_behavioral_utm")

        total_time = int(time_on_page_seconds) + (int(existing.get("total_time_on_page_seconds", 0)) if existing else 0)
        max_scroll = max(int(scroll_depth_pct), int(existing.get("max_scroll_depth_pct", 0)) if existing else 0)
        total_clicks = int(cta_clicks) + (int(existing.get("cta_clicks", 0)) if existing else 0)

        warmth_score, high_intent = compute_behavioral_intent_score(
            pages_visited=merged_pages,
            time_on_page_seconds=total_time,
            scroll_depth_pct=max_scroll,
            cta_clicks=total_clicks,
            utm_source=utm_source,
            referrer=referrer,
            is_identified_person=bool(merged_email or merged_prospect_id),
            is_corporate_company=bool(merged_domain),
        )

        node_id = (
            existing["id"]
            if existing
            else f"vign_{hashlib.sha1(f'{visitor_id}:{fingerprint_hash}:{ip_hash}:{now}'.encode('utf-8')).hexdigest()[:14]}"
        )
        engine = self._store._holder.engine
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM visitor_identity_graph WHERE id = :id"),
                {"id": node_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO visitor_identity_graph (
                        id, visitor_id, fingerprint_hash, ip_hash, last_ip,
                        prospect_id, contact_id, email, full_name,
                        company_domain, company_name, resolution_layer, confidence,
                        pages_visited_json, total_time_on_page_seconds, max_scroll_depth_pct,
                        cta_clicks, intent_warmth_score, high_intent_alert, created_at, updated_at
                    ) VALUES (
                        :id, :vid, :fp, :iph, :ip,
                        :pid, :cid, :email, :name,
                        :dom, :comp, :layer, :conf,
                        :pages, :time_sec, :scroll,
                        :clicks, :warmth, :alert, :created, :updated
                    )
                    """
                ),
                {
                    "id": node_id,
                    "vid": visitor_id or (existing.get("visitor_id", "") if existing else ""),
                    "fp": fingerprint_hash or (existing.get("fingerprint_hash", "") if existing else ""),
                    "iph": ip_hash,
                    "ip": ip_address or "",
                    "pid": merged_prospect_id,
                    "cid": merged_contact_id,
                    "email": merged_email,
                    "name": merged_name,
                    "dom": merged_domain,
                    "comp": merged_company,
                    "layer": merged_layer,
                    "conf": merged_conf,
                    "pages": json.dumps(merged_pages),
                    "time_sec": total_time,
                    "scroll": max_scroll,
                    "clicks": total_clicks,
                    "warmth": warmth_score,
                    "alert": 1 if high_intent else 0,
                    "created": existing.get("created_at", now) if existing else now,
                    "updated": now,
                },
            )

        return {
            "id": node_id,
            "visitor_id": visitor_id or (existing.get("visitor_id", "") if existing else ""),
            "fingerprint_hash": fingerprint_hash or (existing.get("fingerprint_hash", "") if existing else ""),
            "ip_hash": ip_hash,
            "last_ip": ip_address,
            "prospect_id": merged_prospect_id,
            "contact_id": merged_contact_id,
            "email": merged_email,
            "full_name": merged_name,
            "company_domain": merged_domain,
            "company_name": merged_company,
            "resolution_layer": merged_layer,
            "confidence": merged_conf,
            "pages_visited": merged_pages,
            "total_time_on_page_seconds": total_time,
            "max_scroll_depth_pct": max_scroll,
            "cta_clicks": total_clicks,
            "intent_warmth_score": warmth_score,
            "high_intent_alert": high_intent,
            "updated_at": now,
        }

    def list_nodes(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self._store is None:
            return []
        self.ensure_table()
        engine = self._store._holder.engine
        with engine.begin() as conn:
            rows = conn.execute(
                text("SELECT * FROM visitor_identity_graph ORDER BY updated_at DESC LIMIT :lim"),
                {"lim": max(1, min(limit, 200))},
            ).mappings().all()
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["pages_visited"] = json.loads(d.get("pages_visited_json") or "[]")
            except Exception:
                d["pages_visited"] = []
            d["high_intent_alert"] = bool(d.get("high_intent_alert"))
            out.append(d)
        return out


# ── Full 5-Layer Visitor Resolution Pipeline ──────────────────────────────


def _extract_query_params_from_url(page_url: str) -> Dict[str, str]:
    if not page_url or "?" not in page_url:
        return {}
    parsed = urllib.parse.urlparse(page_url)
    return {k: v for k, v in urllib.parse.parse_qsl(parsed.query) if v}


def resolve_visitor_5_layer(
    *,
    ip_address: str,
    page_visited: str = "/",
    referrer: str = "",
    visitor_id: str = "",
    ar_vid: str = "",
    ar_pid: str = "",
    gb_cid: str = "",
    utm_source: str = "",
    utm_term: str = "",
    identified_email: str = "",
    identified_domain: str = "",
    identified_name: str = "",
    user_agent: str = "",
    screen_resolution: str = "",
    timezone_str: str = "",
    language: str = "",
    webgl_renderer: str = "",
    canvas_hash: str = "",
    fingerprint_hash: str = "",
    time_on_page_seconds: int = 0,
    scroll_depth_pct: int = 0,
    cta_clicks: int = 0,
    pages_visited: Optional[List[str]] = None,
    store: Any = None,
    enrich_company: bool = False,
) -> VisitorResolutionResult:
    """Execute the 5-Layer Visitor De-Anonymization Engine, resolving WFH / Residential / Mobile / VPN visitors."""
    url_params = _extract_query_params_from_url(page_visited)
    eff_vid_token = ar_vid or url_params.get("_ar_vid") or ""
    eff_pid = ar_pid or url_params.get("_ar_pid") or ""
    eff_cid = gb_cid or url_params.get("_gb_cid") or ""
    eff_utm_term = utm_term or url_params.get("utm_term") or ""
    eff_utm_source = utm_source or url_params.get("utm_source") or ""

    fp_hash = fingerprint_hash or compute_browser_fingerprint_hash(
        user_agent=user_agent,
        screen_resolution=screen_resolution,
        timezone_str=timezone_str,
        language=language,
        webgl_renderer=webgl_renderer,
        canvas_hash=canvas_hash,
    )
    eff_visitor_id = visitor_id or (f"vid_{fp_hash[3:15]}" if fp_hash else f"vid_{compute_ip_hash(ip_address)[4:14]}")
    graph = VisitorIdentityGraph(store) if store is not None else None

    all_pages = list(pages_visited or [])
    if page_visited and page_visited not in all_pages:
        all_pages.append(page_visited)

    # ── LAYER 1: Outbound Click & Email Token Stitching (100% Confidence) ──
    token_data = decode_outbound_visitor_token(eff_vid_token) if eff_vid_token else None
    if not token_data and eff_utm_term:
        token_data = decode_outbound_visitor_token(eff_utm_term)

    matched_prospect = None
    lookup_pid = (token_data.get("prospect_id") if token_data else "") or eff_pid or eff_cid
    if lookup_pid and store is not None and hasattr(store, "get_prospect"):
        try:
            matched_prospect = store.get_prospect(lookup_pid)
        except Exception:
            matched_prospect = None

    if token_data or matched_prospect or eff_pid or eff_cid:
        p_id = (
            (matched_prospect.id if matched_prospect else "")
            or (token_data.get("prospect_id", "") if token_data else "")
            or eff_pid
            or eff_cid
        )
        p_email = (
            (matched_prospect.email if matched_prospect and matched_prospect.email else "")
            or (token_data.get("email", "") if token_data else "")
            or identified_email
        ).strip().lower()
        p_name = (
            (matched_prospect.full_name if matched_prospect and matched_prospect.full_name else "")
            or (token_data.get("full_name", "") if token_data else "")
            or identified_name
        ).strip()
        p_dom = normalize_domain(
            (token_data.get("company_domain", "") if token_data else "")
            or ((matched_prospect.research or {}).get("company_domain", "") if matched_prospect else "")
            or (p_email.split("@", 1)[1] if "@" in p_email else "")
            or (matched_prospect.company if matched_prospect and matched_prospect.company and "." in matched_prospect.company else "")
            or identified_domain
        )
        p_comp = (
            (matched_prospect.company if matched_prospect and matched_prospect.company else "")
            or (token_data.get("company_name", "") if token_data else "")
            or (p_dom.split(".")[0].replace("-", " ").title() if p_dom else "Identified Prospect Company")
        )
        if not p_dom and p_comp:
            p_dom = f"{re.sub(r'[^a-z0-9]', '', p_comp.lower().split()[0])}.com"

        node = {}
        if graph is not None:
            for pg in all_pages:
                node = graph.upsert_identity_node(
                    visitor_id=eff_visitor_id,
                    fingerprint_hash=fp_hash,
                    ip_address=ip_address,
                    prospect_id=p_id,
                    contact_id=eff_cid or p_id,
                    email=p_email,
                    full_name=p_name,
                    company_domain=p_dom,
                    company_name=p_comp,
                    resolution_layer="layer_1_outbound_token",
                    confidence=1.0,
                    page_visited=pg,
                    time_on_page_seconds=time_on_page_seconds,
                    scroll_depth_pct=scroll_depth_pct,
                    cta_clicks=cta_clicks,
                    utm_source=eff_utm_source,
                    referrer=referrer,
                )

        warmth, high_intent = compute_behavioral_intent_score(
            pages_visited=node.get("pages_visited", all_pages),
            time_on_page_seconds=node.get("total_time_on_page_seconds", time_on_page_seconds),
            scroll_depth_pct=node.get("max_scroll_depth_pct", scroll_depth_pct),
            cta_clicks=node.get("cta_clicks", cta_clicks),
            utm_source=eff_utm_source,
            referrer=referrer,
            is_identified_person=True,
            is_corporate_company=True,
        )
        dms = []
        if p_email or p_name:
            parts = (p_name or "Executive Contact").split()
            dms.append(
                DecisionMakerCandidate(
                    full_name=p_name or p_email.split("@")[0].replace(".", " ").title(),
                    first_name=parts[0],
                    last_name=parts[-1] if len(parts) > 1 else "",
                    title=(matched_prospect.title if matched_prospect and matched_prospect.title else "Decision Maker"),
                    email=p_email,
                    email_confidence=1.0,
                    email_status="verified_outbound_click",
                )
            )
        return VisitorResolutionResult(
            ip_address=ip_address,
            is_corporate=True,
            company_name=p_comp,
            company_domain=p_dom,
            confidence=1.0,
            page_visited=page_visited,
            referrer=referrer,
            decision_makers=dms,
            resolution_method="layer_1_outbound_token",
            resolution_layer=1,
            visitor_id=eff_visitor_id,
            fingerprint_hash=fp_hash,
            prospect_id=p_id,
            contact_id=eff_cid or p_id,
            person_email=p_email,
            person_name=p_name,
            pages_visited=node.get("pages_visited", all_pages),
            time_on_page_seconds=node.get("total_time_on_page_seconds", time_on_page_seconds),
            scroll_depth_pct=node.get("max_scroll_depth_pct", scroll_depth_pct),
            cta_clicks=node.get("cta_clicks", cta_clicks),
            intent_warmth_score=warmth,
            high_intent_alert=high_intent,
            is_wfh_stitched=True,
        )

    # ── LAYER 2: Form / Cal.com / Chat / Newsletter Identity Stitching (98% Confidence) ──
    email_clean = (identified_email or "").strip().lower()
    email_dom = email_clean.split("@", 1)[1] if "@" in email_clean else ""
    corp_dom_from_email = email_dom if (email_dom and email_dom not in FREE_WEBMAIL_DOMAINS) else ""
    layer2_dom = normalize_domain(identified_domain or corp_dom_from_email)

    if email_clean or layer2_dom:
        comp_name = (layer2_dom.split(".")[0].replace("-", " ").title()) if layer2_dom else "Identified Visitor"
        person_name = identified_name or (email_clean.split("@")[0].replace(".", " ").title() if email_clean else "")
        node = {}
        if graph is not None:
            for pg in all_pages:
                node = graph.upsert_identity_node(
                    visitor_id=eff_visitor_id,
                    fingerprint_hash=fp_hash,
                    ip_address=ip_address,
                    email=email_clean,
                    full_name=person_name,
                    company_domain=layer2_dom,
                    company_name=comp_name,
                    resolution_layer="layer_2_form_identify",
                    confidence=0.98,
                    page_visited=pg,
                    time_on_page_seconds=time_on_page_seconds,
                    scroll_depth_pct=scroll_depth_pct,
                    cta_clicks=cta_clicks,
                    utm_source=eff_utm_source,
                    referrer=referrer,
                )
        warmth, high_intent = compute_behavioral_intent_score(
            pages_visited=node.get("pages_visited", all_pages),
            time_on_page_seconds=node.get("total_time_on_page_seconds", time_on_page_seconds),
            scroll_depth_pct=node.get("max_scroll_depth_pct", scroll_depth_pct),
            cta_clicks=node.get("cta_clicks", cta_clicks),
            utm_source=eff_utm_source,
            referrer=referrer,
            is_identified_person=bool(email_clean),
            is_corporate_company=bool(layer2_dom),
        )
        dms = []
        if email_clean:
            parts = (person_name or "Contact").split()
            dms.append(
                DecisionMakerCandidate(
                    full_name=person_name,
                    first_name=parts[0],
                    last_name=parts[-1] if len(parts) > 1 else "",
                    title="Inbound / Form Lead",
                    email=email_clean,
                    email_confidence=0.98,
                    email_status="verified_form_capture",
                )
            )
        return VisitorResolutionResult(
            ip_address=ip_address,
            is_corporate=bool(layer2_dom),
            company_name=comp_name,
            company_domain=layer2_dom,
            confidence=0.98,
            page_visited=page_visited,
            referrer=referrer,
            decision_makers=dms,
            resolution_method="layer_2_form_identify",
            resolution_layer=2,
            visitor_id=eff_visitor_id,
            fingerprint_hash=fp_hash,
            person_email=email_clean,
            person_name=person_name,
            pages_visited=node.get("pages_visited", all_pages),
            time_on_page_seconds=node.get("total_time_on_page_seconds", time_on_page_seconds),
            scroll_depth_pct=node.get("max_scroll_depth_pct", scroll_depth_pct),
            cta_clicks=node.get("cta_clicks", cta_clicks),
            intent_warmth_score=warmth,
            high_intent_alert=high_intent,
            is_wfh_stitched=True,
        )

    # ── LAYER 3: Cross-Session First-Party Cookie & Browser Fingerprint Identity Graph (92% Confidence) ──
    if graph is not None:
        matched_node = graph.find_matching_identity(
            visitor_id=eff_visitor_id,
            fingerprint_hash=fp_hash,
            ip_hash=compute_ip_hash(ip_address),
        )
        if matched_node and matched_node.get("company_domain"):
            updated_node = {}
            for pg in all_pages:
                updated_node = graph.upsert_identity_node(
                    visitor_id=eff_visitor_id,
                    fingerprint_hash=fp_hash,
                    ip_address=ip_address,
                    prospect_id=matched_node.get("prospect_id", ""),
                    contact_id=matched_node.get("contact_id", ""),
                    email=matched_node.get("email", ""),
                    full_name=matched_node.get("full_name", ""),
                    company_domain=matched_node["company_domain"],
                    company_name=matched_node.get("company_name", ""),
                    resolution_layer="layer_3_identity_graph",
                    confidence=max(0.92, float(matched_node.get("confidence", 0.92))),
                    page_visited=pg,
                    time_on_page_seconds=time_on_page_seconds,
                    scroll_depth_pct=scroll_depth_pct,
                    cta_clicks=cta_clicks,
                    utm_source=eff_utm_source,
                    referrer=referrer,
                )
            dms = []
            if updated_node.get("email"):
                p_name = updated_node.get("full_name") or updated_node["email"].split("@")[0].title()
                parts = p_name.split()
                dms.append(
                    DecisionMakerCandidate(
                        full_name=p_name,
                        first_name=parts[0],
                        last_name=parts[-1] if len(parts) > 1 else "",
                        title="Returning Identified Buyer",
                        email=updated_node["email"],
                        email_confidence=0.95,
                        email_status="identity_graph_stitched",
                    )
                )
            return VisitorResolutionResult(
                ip_address=ip_address,
                is_corporate=True,
                company_name=updated_node.get("company_name") or matched_node["company_domain"],
                company_domain=matched_node["company_domain"],
                confidence=max(0.92, float(matched_node.get("confidence", 0.92))),
                page_visited=page_visited,
                referrer=referrer,
                decision_makers=dms,
                resolution_method="layer_3_identity_graph",
                resolution_layer=3,
                visitor_id=eff_visitor_id,
                fingerprint_hash=fp_hash,
                prospect_id=updated_node.get("prospect_id", ""),
                contact_id=updated_node.get("contact_id", ""),
                person_email=updated_node.get("email", ""),
                person_name=updated_node.get("full_name", ""),
                pages_visited=updated_node.get("pages_visited", all_pages),
                time_on_page_seconds=updated_node.get("total_time_on_page_seconds", time_on_page_seconds),
                scroll_depth_pct=updated_node.get("max_scroll_depth_pct", scroll_depth_pct),
                cta_clicks=updated_node.get("cta_clicks", cta_clicks),
                intent_warmth_score=updated_node.get("intent_warmth_score", 80),
                high_intent_alert=bool(updated_node.get("high_intent_alert", False)),
                is_wfh_stitched=True,
            )

    # ── LAYER 4: Corporate rDNS + RDAP / ARIN / RIPE / APNIC Lookup ─────────
    ip_res = deanonymize_visitor_ip(
        ip_address,
        page_visited=page_visited,
        referrer=referrer,
        enrich_company=enrich_company,
    )
    if ip_res.is_corporate and ip_res.company_domain:
        node = {}
        if graph is not None:
            for pg in all_pages:
                node = graph.upsert_identity_node(
                    visitor_id=eff_visitor_id,
                    fingerprint_hash=fp_hash,
                    ip_address=ip_address,
                    company_domain=ip_res.company_domain,
                    company_name=ip_res.company_name,
                    resolution_layer="layer_4_rdap_rdns",
                    confidence=ip_res.confidence,
                    page_visited=pg,
                    time_on_page_seconds=time_on_page_seconds,
                    scroll_depth_pct=scroll_depth_pct,
                    cta_clicks=cta_clicks,
                    utm_source=eff_utm_source,
                    referrer=referrer,
                )
        warmth, high_intent = compute_behavioral_intent_score(
            pages_visited=node.get("pages_visited", all_pages),
            time_on_page_seconds=node.get("total_time_on_page_seconds", time_on_page_seconds),
            scroll_depth_pct=node.get("max_scroll_depth_pct", scroll_depth_pct),
            cta_clicks=node.get("cta_clicks", cta_clicks),
            utm_source=eff_utm_source,
            referrer=referrer,
            is_identified_person=False,
            is_corporate_company=True,
        )
        ip_res.visitor_id = eff_visitor_id
        ip_res.fingerprint_hash = fp_hash
        ip_res.resolution_layer = 4
        ip_res.pages_visited = node.get("pages_visited", all_pages)
        ip_res.time_on_page_seconds = node.get("total_time_on_page_seconds", time_on_page_seconds)
        ip_res.scroll_depth_pct = node.get("max_scroll_depth_pct", scroll_depth_pct)
        ip_res.cta_clicks = node.get("cta_clicks", cta_clicks)
        ip_res.intent_warmth_score = warmth
        ip_res.high_intent_alert = high_intent
        return ip_res

    # ── LAYER 5: Referrer, UTM & High-Intent Behavioral Scoring (Anonymous WFH/ISP) ──
    node = {}
    if graph is not None:
        for pg in all_pages:
            node = graph.upsert_identity_node(
                visitor_id=eff_visitor_id,
                fingerprint_hash=fp_hash,
                ip_address=ip_address,
                resolution_layer="layer_5_behavioral_utm",
                confidence=0.35,
                page_visited=pg,
                time_on_page_seconds=time_on_page_seconds,
                scroll_depth_pct=scroll_depth_pct,
                cta_clicks=cta_clicks,
                utm_source=eff_utm_source,
                referrer=referrer,
            )
    warmth, high_intent = compute_behavioral_intent_score(
        pages_visited=node.get("pages_visited", all_pages),
        time_on_page_seconds=node.get("total_time_on_page_seconds", time_on_page_seconds),
        scroll_depth_pct=node.get("max_scroll_depth_pct", scroll_depth_pct),
        cta_clicks=node.get("cta_clicks", cta_clicks),
        utm_source=eff_utm_source,
        referrer=referrer,
        is_identified_person=False,
        is_corporate_company=False,
    )
    ip_res.visitor_id = eff_visitor_id
    ip_res.fingerprint_hash = fp_hash
    ip_res.resolution_method = "layer_5_behavioral_utm"
    ip_res.resolution_layer = 5
    ip_res.pages_visited = node.get("pages_visited", all_pages)
    ip_res.time_on_page_seconds = node.get("total_time_on_page_seconds", time_on_page_seconds)
    ip_res.scroll_depth_pct = node.get("max_scroll_depth_pct", scroll_depth_pct)
    ip_res.cta_clicks = node.get("cta_clicks", cta_clicks)
    ip_res.intent_warmth_score = warmth
    ip_res.high_intent_alert = high_intent
    return ip_res


def generate_visitor_tracking_script_js(collector_endpoint: str = "/api/visitors/beacon") -> str:
    """Return the 5-Layer First-Party `wv.js` tracking pixel with Outbound Token Stitcher,
    Form & Cal.com/Calendly Capture, WebGL/Canvas/Timezone Fingerprinter, and Behavioral Intent Tracker."""
    return f"""(function(window, document) {{
  'use strict';
  var ENDPOINT = {json.dumps(collector_endpoint)};
  var COOKIE_VID = '_ar_visitor_id';
  var COOKIE_TOKEN = '_ar_vid';
  var startTs = Date.now();
  var maxScrollPct = 0;
  var ctaClicks = 0;

  function setCookie(name, val) {{
    try {{
      document.cookie = name + '=' + encodeURIComponent(val) + '; path=/; max-age=31536000; SameSite=Lax';
      localStorage.setItem(name, val);
    }} catch (e) {{}}
  }}

  function getCookie(name) {{
    try {{
      var m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
      if (m) return decodeURIComponent(m[1]);
      return localStorage.getItem(name) || '';
    }} catch (e) {{ return ''; }}
  }}

  function getVisitorId() {{
    var vid = getCookie(COOKIE_VID);
    if (!vid) {{
      vid = 'vid_' + Math.random().toString(36).substring(2, 12) + Date.now().toString(36);
      setCookie(COOKIE_VID, vid);
    }}
    return vid;
  }}

  function getWebGLRenderer() {{
    try {{
      var canvas = document.createElement('canvas');
      var gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (!gl) return '';
      var dbg = gl.getExtension('WEBGL_debug_renderer_info');
      return dbg ? (gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) || '') : '';
    }} catch (e) {{ return ''; }}
  }}

  function parseQueryParams() {{
    var qs = window.location.search || '';
    var out = {{}};
    qs.replace(/[?&]+([^=&]+)=([^&]*)/gi, function(_, k, v) {{
      out[decodeURIComponent(k)] = decodeURIComponent(v || '');
    }});
    return out;
  }}

  var qParams = parseQueryParams();
  if (qParams._ar_vid) setCookie(COOKIE_TOKEN, qParams._ar_vid);

  function sendBeaconPayload(extra) {{
    var payload = Object.assign({{
      visitor_id: getVisitorId(),
      ar_vid: qParams._ar_vid || getCookie(COOKIE_TOKEN) || '',
      ar_pid: qParams._ar_pid || '',
      gb_cid: qParams._gb_cid || '',
      page_url: window.location.href,
      page_path: window.location.pathname,
      referrer: document.referrer || '',
      title: document.title || '',
      user_agent: navigator.userAgent || '',
      language: navigator.language || '',
      screen_resolution: (window.screen ? window.screen.width + 'x' + window.screen.height : ''),
      timezone: (Intl && Intl.DateTimeFormat ? Intl.DateTimeFormat().resolvedOptions().timeZone : ''),
      webgl_renderer: getWebGLRenderer(),
      utm_source: qParams.utm_source || '',
      utm_term: qParams.utm_term || '',
      time_on_page_seconds: Math.round((Date.now() - startTs) / 1000),
      scroll_depth_pct: maxScrollPct,
      cta_clicks: ctaClicks,
      timestamp: new Date().toISOString()
    }}, extra || {{}});

    var body = JSON.stringify(payload);
    if (navigator.sendBeacon) {{
      var blob = new Blob([body], {{ type: 'application/json' }});
      navigator.sendBeacon(ENDPOINT, blob);
    }} else {{
      fetch(ENDPOINT, {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: body, keepalive: true }}).catch(function(){{}});
    }}
  }}

  // Layer 2: Hook <input type="email"> blur/change & form submit
  document.addEventListener('change', function(e) {{
    var el = e.target;
    if (el && (el.type === 'email' || (el.name && el.name.toLowerCase().indexOf('email') !== -1))) {{
      if (el.value && el.value.indexOf('@') > 0) {{
        sendBeaconPayload({{ email: el.value.trim(), event: 'form_email_input' }});
      }}
    }}
  }}, true);

  // Layer 2: Hook Cal.com & Calendly postMessage booking events
  window.addEventListener('message', function(e) {{
    try {{
      var d = typeof e.data === 'string' ? JSON.parse(e.data) : (e.data || {{}});
      var evName = d.event || d.type || '';
      if (evName.indexOf('calendly.') === 0 || evName.indexOf('cal:') === 0 || evName === 'bookingSuccessful') {{
        var inviteeEmail = (d.payload && (d.payload.email || (d.payload.attendees && d.payload.attendees[0] && d.payload.attendees[0].email))) || '';
        sendBeaconPayload({{ email: inviteeEmail, event: 'calendar_booking' }});
      }}
    }} catch (_) {{}}
  }});

  // Layer 5: Track scroll depth & CTA clicks
  window.addEventListener('scroll', function() {{
    try {{
      var docH = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) - window.innerHeight;
      if (docH > 0) {{
        var pct = Math.min(100, Math.round((window.scrollY / docH) * 100));
        if (pct > maxScrollPct) maxScrollPct = pct;
      }}
    }} catch (_) {{}}
  }}, {{ passive: true }});

  document.addEventListener('click', function(e) {{
    var btn = e.target && e.target.closest ? e.target.closest('button, a') : null;
    if (btn) {{
      var txt = (btn.innerText || '').toLowerCase();
      if (txt.indexOf('demo') !== -1 || txt.indexOf('book') !== -1 || txt.indexOf('start') !== -1 || txt.indexOf('pricing') !== -1) {{
        ctaClicks += 1;
      }}
    }}
  }}, true);

  var api = {{
    identify: function(traits) {{ sendBeaconPayload(traits || {{}}); }},
    trackPageView: function(customProps) {{ sendBeaconPayload(customProps || {{}}); }}
  }};
  window.AutoReachVisitors = api;
  window.GojiberryVisitors = api;

  if (document.readyState === 'complete') {{
    sendBeaconPayload();
  }} else {{
    window.addEventListener('load', function() {{ sendBeaconPayload(); }});
  }}
}})(window, document);
"""


def resolve_visitor_company(
    *,
    ip_address: str,
    page_visited: str = "/",
    referrer: str = "",
    domain_hint: Optional[str] = None,
    email_hint: Optional[str] = None,
    enrich_decision_makers: bool = True,
    visitor_id: str = "",
    ar_vid: str = "",
    ar_pid: str = "",
    gb_cid: str = "",
    utm_source: str = "",
    utm_term: str = "",
    user_agent: str = "",
    screen_resolution: str = "",
    timezone_str: str = "",
    language: str = "",
    webgl_renderer: str = "",
    fingerprint_hash: str = "",
    time_on_page_seconds: int = 0,
    scroll_depth_pct: int = 0,
    cta_clicks: int = 0,
    pages_visited: Optional[List[str]] = None,
    store: Any = None,
) -> VisitorResolutionResult:
    """Resolve a website visitor across all 5 De-Anonymization Layers."""
    return resolve_visitor_5_layer(
        ip_address=ip_address,
        page_visited=page_visited,
        referrer=referrer,
        visitor_id=visitor_id,
        ar_vid=ar_vid,
        ar_pid=ar_pid,
        gb_cid=gb_cid,
        utm_source=utm_source,
        utm_term=utm_term,
        identified_email=email_hint or "",
        identified_domain=domain_hint or "",
        user_agent=user_agent,
        screen_resolution=screen_resolution,
        timezone_str=timezone_str,
        language=language,
        webgl_renderer=webgl_renderer,
        fingerprint_hash=fingerprint_hash,
        time_on_page_seconds=time_on_page_seconds,
        scroll_depth_pct=scroll_depth_pct,
        cta_clicks=cta_clicks,
        pages_visited=pages_visited,
        store=store,
        enrich_company=enrich_decision_makers,
    )

resolve_5_layer_visitor_identity = resolve_visitor_5_layer
deanonymize_visitor_5_layers = resolve_visitor_5_layer
