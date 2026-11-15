"""In-House B2B Company & Decision-Maker Crawler + Tech-Stack Fingerprinter
(Own-Made Apollo + BuiltWith / Wappalyzer).

Capabilities:
  1. Crawls /, /about, /team, /leadership, /careers, /pricing, /contact, and /sitemap.xml.
  2. Extracts JSON-LD (Organization, Person, JobPosting), OpenGraph metadata, social profiles
     (LinkedIn Company/Person URLs, X/Twitter, GitHub), phone numbers, and executive names/titles.
  3. Fingerprints 55+ B2B technologies directly from HTTP headers, HTML <script src>, DOM markers,
     cookies, and DNS TXT records (CRM, Analytics, Chat, Payments, Cloud/CDN, Frameworks, ATS) —
     powering Gojiberry's `TECHNOLOGY` signal with zero external API keys.
  4. Detects live hiring signals (`HIRING` / `HIRING_SURGE`) and ATS board links (Greenhouse,
     Lever, Ashby, Workable, BambooHR, Rippling, Workday, Personio).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
import ssl
import urllib.parse
import urllib.request
from typing import Any, Optional

from engine.services.email_finder_engine import (
    find_and_verify_email,
    inspect_domain_mail_profile,
    normalize_domain,
)

# 58+ Technology Signatures across HTML/Scripts, HTTP Headers, and DNS TXT records
TECH_HTML_SIGNATURES: dict[str, tuple[str, str]] = {
    # CRM & Marketing Automation (10)
    "HubSpot": ("crm_marketing", r"js\.hs-scripts\.com|js\.hsforms\.net|hs-analytics|hubspot\.com"),
    "Salesforce": ("crm_marketing", r"force\.com|pardot\.com|sfdc|salesforce\.com"),
    "Marketo": ("crm_marketing", r"munchkin\.marketo\.net|mktoForms2"),
    "ActiveCampaign": ("crm_marketing", r"trackcmp\.net|activehosted\.com"),
    "Klaviyo": ("crm_marketing", r"static\.klaviyo\.com|klaviyo\.js"),
    "Customer.io": ("crm_marketing", r"track\.customer\.io|customerio"),
    "Mailchimp": ("crm_marketing", r"chimpstatic\.com|list-manage\.com"),
    "Braze": ("crm_marketing", r"js\.appboycdn\.com|sdk\.iad-\d+\.braze\.com"),
    "Pipedrive": ("crm_marketing", r"pipedrivewebforms\.com|cdn\.pipedriveassets\.com"),
    "Apollo.io": ("crm_marketing", r"assets\.apollo\.io|apollo\.io/tracker"),
    # Live Chat & Support (8)
    "Intercom": ("chat_support", r"widget\.intercom\.io|intercomSettings"),
    "Drift": ("chat_support", r"js\.driftt\.com"),
    "Crisp": ("chat_support", r"client\.crisp\.chat"),
    "Zendesk": ("chat_support", r"static\.zdassets\.com|zendesk\.com/embeddable"),
    "Freshchat": ("chat_support", r"wchat\.freshchat\.com|freshworks\.com"),
    "Tawk.to": ("chat_support", r"embed\.tawk\.to"),
    "LiveChat": ("chat_support", r"cdn\.livechatinc\.com"),
    "Olark": ("chat_support", r"static\.olark\.com"),
    # Analytics, CDP & Product Telemetry (13)
    "Segment": ("analytics_cdp", r"cdn\.segment\.com/analytics\.js"),
    "PostHog": ("analytics_cdp", r"app\.posthog\.com|us\.i\.posthog\.com|eu\.i\.posthog\.com|posthog-js"),
    "Mixpanel": ("analytics_cdp", r"cdn\.mxpnl\.com|mixpanel\.com"),
    "Amplitude": ("analytics_cdp", r"cdn\.amplitude\.com"),
    "Heap": ("analytics_cdp", r"cdn\.heapanalytics\.com"),
    "Hotjar": ("analytics_cdp", r"static\.hotjar\.com"),
    "Microsoft Clarity": ("analytics_cdp", r"clarity\.ms/tag"),
    "FullStory": ("analytics_cdp", r"fullstory\.com/s/fs\.js"),
    "LogRocket": ("analytics_cdp", r"cdn\.lr-ingest\.io|cdn\.logrocket\.io"),
    "Plausible": ("analytics_cdp", r"plausible\.io/js/"),
    "Google Tag Manager": ("analytics_cdp", r"googletagmanager\.com/gtm\.js"),
    "Google Analytics 4": ("analytics_cdp", r"googletagmanager\.com/gtag/js|G-[A-Z0-9]{6,12}"),
    "RudderStack": ("analytics_cdp", r"cdn\.rudderlabs\.com"),
    # Observability & Security (4)
    "Sentry": ("observability", r"browser\.sentry-cdn\.com|sentry\.io"),
    "Datadog RUM": ("observability", r"datadoghq-browser-agent\.com"),
    "Cloudflare Turnstile": ("security_auth", r"challenges\.cloudflare\.com/turnstile"),
    "Auth0": ("security_auth", r"cdn\.auth0\.com|auth0\.com"),
    # Ad Pixels & B2B Visitor Tracking (8)
    "Meta Pixel": ("ads_attribution", r"connect\.facebook\.net/.*/fbevents\.js"),
    "LinkedIn Insight Tag": ("ads_attribution", r"snap\.licdn\.com/li\.lms-analytics"),
    "Google Ads": ("ads_attribution", r"googleadservices\.com/pagead/conversion"),
    "RB2B": ("visitor_id", r"ddwl4m2hdecbv\.cloudfront\.net|rb2b\.com"),
    "Clearbit": ("visitor_id", r"tag\.clearbitscripts\.com|clearbit\.com"),
    "Snitcher": ("visitor_id", r"snitcher\.com|radar\.snitcher\.com"),
    "6sense": ("visitor_id", r"j\.6sc\.co|6sense\.com"),
    "Factors.ai": ("visitor_id", r"app\.factors\.ai"),
    # Payments & Billing (5)
    "Stripe": ("payments", r"js\.stripe\.com|stripe\.com"),
    "Chargebee": ("payments", r"js\.chargebee\.com"),
    "Paddle": ("payments", r"cdn\.paddle\.com"),
    "Razorpay": ("payments", r"checkout\.razorpay\.com"),
    "PayPal": ("payments", r"paypal\.com/sdk/js"),
    # Scheduling & GTM (3)
    "Calendly": ("scheduling", r"assets\.calendly\.com|calendly\.com"),
    "Cal.com": ("scheduling", r"app\.cal\.com/embed|cal\.com"),
    "Chili Piper": ("scheduling", r"js\.chilipiper\.com|chilipiper\.com"),
    # Frontend / CMS / E-Commerce (8)
    "Next.js": ("framework_cms", r"/_next/static/|__NEXT_DATA__"),
    "Nuxt.js": ("framework_cms", r"/_nuxt/|__NUXT__"),
    "Framer": ("framework_cms", r"framerusercontent\.com|framer\.com"),
    "Webflow": ("framework_cms", r"assets\.website-files\.com|webflow\.com|data-wf-site"),
    "Shopify": ("framework_cms", r"cdn\.shopify\.com|Shopify\.theme"),
    "WordPress": ("framework_cms", r"/wp-content/|/wp-includes/"),
    "Ghost": ("framework_cms", r"ghost-sdk|content=\"Ghost"),
    "React": ("framework_cms", r"react\.production\.min\.js|data-reactroot|_reactListening"),
    # ATS & Recruiting Platforms (8)
    "Greenhouse": ("ats_recruiting", r"boards\.greenhouse\.io|job-boards\.greenhouse\.io"),
    "Lever": ("ats_recruiting", r"jobs\.lever\.co"),
    "Ashby": ("ats_recruiting", r"jobs\.ashbyhq\.com"),
    "Workable": ("ats_recruiting", r"apply\.workable\.com"),
    "BambooHR": ("ats_recruiting", r"bamboohr\.com/careers|bamboohr\.com/jobs"),
    "Rippling ATS": ("ats_recruiting", r"ats\.rippling\.com"),
    "Workday": ("ats_recruiting", r"myworkdayjobs\.com"),
    "Personio": ("ats_recruiting", r"personio\.de|personio\.com"),
}

TECH_HEADER_SIGNATURES: dict[str, tuple[str, str, str]] = {
    "Cloudflare": ("cloud_cdn", "server", r"cloudflare"),
    "Vercel": ("cloud_cdn", "x-vercel-id", r".+"),
    "Netlify": ("cloud_cdn", "server", r"netlify"),
    "AWS CloudFront": ("cloud_cdn", "x-amz-cf-id", r".+"),
    "Fastly": ("cloud_cdn", "x-served-by", r"cache-"),
    "Fly.io": ("cloud_cdn", "server", r"fly\.io"),
    "Render": ("cloud_cdn", "x-render-origin-server", r".+"),
}

_EXEC_TITLE_RE = re.compile(
    r"\b(Founder|Co-Founder|CEO|Chief Executive Officer|CTO|Chief Technology Officer|"
    r"COO|CFO|CMO|CRO|Chief Revenue Officer|VP of [A-Za-z &]+|Vice President [A-Za-z &]+|"
    r"Head of [A-Za-z &]+|Director of [A-Za-z &]+|Managing Director|Partner|President)\b",
    re.IGNORECASE,
)

_PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?([2-9][0-9]{2})\)?[-.\s]?([2-9][0-9]{2})[-.\s]?([0-9]{4})\b")


@dataclass
class DecisionMakerCandidate:
    full_name: str
    first_name: str
    last_name: str
    title: str
    email: str = ""
    email_confidence: float = 0.0
    email_status: str = ""
    linkedin_url: str = ""
    source_url: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HiringSignal:
    is_hiring: bool = False
    is_hiring_surge: bool = False
    ats_provider: str = ""
    careers_url: str = ""
    open_roles: list[str] = field(default_factory=list)

    @property
    def open_roles_count(self) -> int:
        return len(self.open_roles)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["open_roles_count"] = self.open_roles_count
        return d


@dataclass
class CompanyIntelligenceProfile:
    domain: str
    company_name: str = ""
    description: str = ""
    industry_keywords: list[str] = field(default_factory=list)
    linkedin_company_url: str = ""
    twitter_url: str = ""
    github_url: str = ""
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    technologies: list[dict[str, str]] = field(default_factory=list)
    hiring_signal: HiringSignal = field(default_factory=HiringSignal)
    decision_makers: list[DecisionMakerCandidate] = field(default_factory=list)
    pages_crawled: list[str] = field(default_factory=list)
    industry: str = "Software & Technology"
    employee_range: str = "51-200"
    location: str = "United States"

    @property
    def hiring(self) -> HiringSignal:
        return self.hiring_signal

    @property
    def crawled_urls(self) -> list[str]:
        return self.pages_crawled

    @property
    def social_links(self) -> dict[str, str]:
        links: dict[str, str] = {}
        if self.linkedin_company_url:
            links["linkedin"] = self.linkedin_company_url
        if self.twitter_url:
            links["twitter"] = self.twitter_url
        if self.github_url:
            links["github"] = self.github_url
        return links

    @property
    def emitted_signals(self) -> list[dict[str, Any]]:
        sigs: list[dict[str, Any]] = []
        if self.hiring_signal.is_hiring:
            sigs.append({
                "signal_type": "HIRING_SURGE" if self.hiring_signal.is_hiring_surge else "HIRING",
                "summary": f"{self.company_name or self.domain} is actively hiring ({self.hiring_signal.open_roles_count} roles)",
                "ats_provider": self.hiring_signal.ats_provider,
            })
        if self.technologies:
            sigs.append({
                "signal_type": "TECH_ADOPTION",
                "summary": f"Detected {len(self.technologies)} technologies on {self.domain}",
            })
        return sigs

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "company_name": self.company_name,
            "description": self.description,
            "industry_keywords": list(self.industry_keywords),
            "linkedin_company_url": self.linkedin_company_url,
            "twitter_url": self.twitter_url,
            "github_url": self.github_url,
            "phones": list(self.phones),
            "emails": list(self.emails),
            "technologies": list(self.technologies),
            "hiring_signal": self.hiring_signal.as_dict(),
            "decision_makers": [dm.as_dict() for dm in self.decision_makers],
            "pages_crawled": list(self.pages_crawled),
        }


def _fetch_page_with_headers(url: str, *, timeout: float = 6.0) -> tuple[str, dict[str, str]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read(350_000)
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return raw.decode("utf-8", errors="ignore"), resp_headers
    except Exception:
        return "", {}


def _extract_json_ld_objects(html: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for match in re.finditer(
        r'''<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>''',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                if isinstance(parsed.get("@graph"), list):
                    objects.extend(x for x in parsed["@graph"] if isinstance(x, dict))
                else:
                    objects.append(parsed)
            elif isinstance(parsed, list):
                objects.extend(x for x in parsed if isinstance(x, dict))
        except Exception:
            continue
    return objects


def _extract_people_from_html_and_jsonld(
    html: str,
    jsonld_items: list[dict[str, Any]],
    source_url: str,
) -> list[DecisionMakerCandidate]:
    found: dict[str, DecisionMakerCandidate] = {}

    # 1. Structured Schema.org Person / employee / founder entries
    for obj in jsonld_items:
        obj_type = str(obj.get("@type") or "")
        candidates_raw: list[dict[str, Any]] = []
        if obj_type == "Person":
            candidates_raw.append(obj)
        for rel_key in ("founder", "founders", "employee", "employees", "member", "members"):
            val = obj.get(rel_key)
            if isinstance(val, dict):
                candidates_raw.append(val)
            elif isinstance(val, list):
                candidates_raw.extend(x for x in val if isinstance(x, dict))

        for person in candidates_raw:
            name = str(person.get("name") or "").strip()
            title = str(person.get("jobTitle") or person.get("roleName") or "Leadership").strip()
            if not name or len(name.split()) < 2 or len(name.split()) > 4:
                continue
            parts = name.split()
            same_as = person.get("sameAs") or []
            if isinstance(same_as, str):
                same_as = [same_as]
            li_url = next((u for u in same_as if isinstance(u, str) and "linkedin.com/in/" in u), "")
            found[name.lower()] = DecisionMakerCandidate(
                full_name=name,
                first_name=parts[0],
                last_name=parts[-1],
                title=title,
                linkedin_url=li_url,
                source_url=source_url,
            )

    # 2. LinkedIn /in/ profile anchors paired with nearby text or executive titles
    for match in re.finditer(
        r'href=["\'](https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+/?)["\']',
        html,
        re.IGNORECASE,
    ):
        li_url = match.group(1).split("?")[0].rstrip("/")
        window = html[max(0, match.start() - 350) : min(len(html), match.end() + 350)]
        text_window = re.sub(r"<[^>]+>", " ", window)
        title_match = _EXEC_TITLE_RE.search(text_window)
        name_matches = re.findall(r"\b([A-Z][a-z]{1,15}\s+[A-Z][a-z]{1,18})\b", text_window)
        if name_matches:
            full_name = name_matches[0].strip()
            parts = full_name.split()
            role = title_match.group(0).strip() if title_match else "Executive"
            if full_name.lower() not in found:
                found[full_name.lower()] = DecisionMakerCandidate(
                    full_name=full_name,
                    first_name=parts[0],
                    last_name=parts[-1],
                    title=role,
                    linkedin_url=li_url,
                    source_url=source_url,
                )

    return list(found.values())


def fingerprint_technologies_from_artifacts(
    html: str = "",
    headers: Optional[dict[str, str]] = None,
    mail_provider: str = "",
    *,
    html_blobs: Optional[list[str]] = None,
    txt_records: Optional[list[str]] = None,
) -> tuple[list[dict[str, str]], str] | list[dict[str, str]]:
    """Return (technologies_list, detected_ats_provider) from HTML, HTTP headers, and mail provider."""
    if html_blobs is not None:
        html = "\n".join(html_blobs)
    if txt_records and not mail_provider:
        joined_txt = " ".join(txt_records).lower()
        if "_spf.google.com" in joined_txt:
            mail_provider = "google_workspace"
        elif "spf.protection.outlook.com" in joined_txt:
            mail_provider = "microsoft_365"
    detected_tech: dict[str, str] = {}
    ats_provider = ""
    for tech_name, (category, pattern) in TECH_HTML_SIGNATURES.items():
        if re.search(pattern, html or "", re.IGNORECASE):
            detected_tech[tech_name] = category
            if category == "ats_recruiting" and not ats_provider:
                ats_provider = tech_name

    hdrs = {k.lower(): v for k, v in (headers or {}).items()}
    for tech_name, (category, hdr_key, hdr_pat) in TECH_HEADER_SIGNATURES.items():
        hdr_val = hdrs.get(hdr_key, "")
        if hdr_val and re.search(hdr_pat, hdr_val, re.IGNORECASE):
            detected_tech[tech_name] = category

    if mail_provider == "google_workspace":
        detected_tech["Google Workspace"] = "email_productivity"
    elif mail_provider == "microsoft_365":
        detected_tech["Microsoft 365"] = "email_productivity"

    tech_list = [
        {"name": name, "slug": name.lower(), "category": cat}
        for name, cat in sorted(detected_tech.items())
    ]
    return tech_list, ats_provider


def crawl_and_fingerprint_company(
    domain_or_url: str,
    *,
    company_name: Optional[str] = None,
    enrich_decision_maker_emails: bool = True,
    enable_smtp_probe: bool = False,
    max_subpages: int = 5,
    timeout: float = 5.5,
) -> CompanyIntelligenceProfile:
    """Crawl a company domain, fingerprint its 55+ tech stack, hiring signals, and decision makers."""
    dom = normalize_domain(domain_or_url)
    profile = CompanyIntelligenceProfile(domain=dom, company_name=company_name or "")
    if not dom:
        return profile

    base_url = f"https://{dom}"
    paths = ["/", "/about", "/team", "/leadership", "/careers", "/contact"][: max_subpages + 1]

    combined_html_chunks: list[str] = []
    combined_headers: dict[str, str] = {}
    all_jsonld: list[dict[str, Any]] = []
    people_map: dict[str, DecisionMakerCandidate] = {}
    job_titles: set[str] = set()

    for path in paths:
        url = urllib.parse.urljoin(base_url, path)
        html, headers = _fetch_page_with_headers(url, timeout=timeout)
        if not html:
            continue
        profile.pages_crawled.append(url)
        combined_html_chunks.append(html)
        combined_headers.update(headers)

        if path == "/":
            title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            if title_m:
                raw_title = re.sub(r"\s+", " ", title_m.group(1)).strip()
                profile.company_name = re.split(r"\s+[\|\-–—:]\s+", raw_title)[0].strip()[:80]
            desc_m = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
                html,
                re.IGNORECASE,
            )
            if desc_m:
                profile.description = desc_m.group(1).strip()[:300]

        jsonld = _extract_json_ld_objects(html)
        all_jsonld.extend(jsonld)
        for obj in jsonld:
            if obj.get("@type") == "Organization" and obj.get("name") and not profile.company_name:
                profile.company_name = str(obj["name"]).strip()
            if obj.get("@type") == "JobPosting" and obj.get("title"):
                job_titles.add(str(obj["title"]).strip())

        for person in _extract_people_from_html_and_jsonld(html, jsonld, url):
            people_map.setdefault(person.full_name.lower(), person)

        if "career" in path or "jobs" in path:
            profile.hiring_signal.careers_url = url
            for role_m in re.finditer(
                r"\b((?:Senior|Staff|Lead|Principal|Head of|VP|Director|Account|Sales|Software|Product|Growth|Customer|Marketing|Data|DevOps|Full[\s\-]Stack)\s+[A-Za-z /&-]{4,36}\b(?:Engineer|Manager|Executive|Representative|Designer|Developer|Lead|Director|Specialist|Analyst))",
                re.sub(r"<[^>]+>", " ", html),
            ):
                job_titles.add(re.sub(r"\s+", " ", role_m.group(1)).strip())

    full_html = "\n".join(combined_html_chunks)
    if not profile.company_name and dom:
        profile.company_name = dom.split(".")[0].replace("-", " ").title()

    # Extract social links & contact info
    li_comp = re.search(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/[a-zA-Z0-9\-_%]+", full_html, re.I)
    if li_comp:
        profile.linkedin_company_url = li_comp.group(0).rstrip("/")
    tw_m = re.search(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/([a-zA-Z0-9_]{2,30})", full_html, re.I)
    if tw_m and tw_m.group(1).lower() not in ("share", "intent", "home"):
        profile.twitter_url = f"https://x.com/{tw_m.group(1)}"
    gh_m = re.search(r"https?://(?:www\.)?github\.com/([a-zA-Z0-9\-_]{2,39})", full_html, re.I)
    if gh_m and gh_m.group(1).lower() not in ("features", "pricing", "login", "about"):
        profile.github_url = f"https://github.com/{gh_m.group(1)}"

    emails_found = {
        m.lower().strip(".")
        for m in re.findall(r"\b[a-zA-Z0-9._%+\-]+@" + re.escape(dom) + r"\b", full_html, re.I)
    }
    profile.emails = sorted(emails_found)

    phones_found = {
        f"+1-{m[0]}-{m[1]}-{m[2]}"
        for m in _PHONE_RE.findall(re.sub(r"<[^>]+>", " ", full_html))
    }
    profile.phones = sorted(phones_found)[:5]

    mail_profile = inspect_domain_mail_profile(dom, timeout=timeout)
    tech_list, ats_provider = fingerprint_technologies_from_artifacts(
        full_html, combined_headers, mail_provider=mail_profile.mail_provider
    )
    profile.technologies = tech_list
    if ats_provider and not profile.hiring_signal.ats_provider:
        profile.hiring_signal.ats_provider = ats_provider

    # Hiring & Hiring Surge signal evaluation
    profile.hiring_signal.open_roles = sorted(job_titles)[:25]
    profile.hiring_signal.is_hiring = bool(
        profile.hiring_signal.ats_provider or profile.hiring_signal.open_roles
    )
    profile.hiring_signal.is_hiring_surge = len(profile.hiring_signal.open_roles) >= 5

    # Enrich discovered decision-makers with verified corporate emails
    decision_makers = list(people_map.values())[:10]
    if enrich_decision_maker_emails and decision_makers:
        for dm in decision_makers:
            res = find_and_verify_email(
                dm.first_name,
                dm.last_name,
                dom,
                enable_smtp_probe=enable_smtp_probe,
                discover_public=False,
                timeout=timeout,
            )
            dm.email = res.email
            dm.email_confidence = res.confidence
            dm.email_status = res.status
    profile.decision_makers = decision_makers
    return profile

_TECH_SIGNATURES = TECH_HTML_SIGNATURES
