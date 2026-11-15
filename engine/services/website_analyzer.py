"""Website evidence crawl + ICP inference for onboarding.

Extracts only what the pages actually contain (title, meta, Open Graph, JSON-LD,
visible copy, extra paths). Never invents a generic B2B SaaS executive ICP.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Optional

from engine.llm.gemini import _ssl_context

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)

EXTRA_PATHS = ("/about", "/pricing", "/manifest.json", "/login")

# Titles the model / old defaults love to invent. Allowed only if the page
# itself mentions that role.
GENERIC_SAAS_TITLES = (
    "head of sales",
    "vp revenue",
    "vp of revenue",
    "vp of sales",
    "vice president of sales",
    "vice president of revenue",
    "chief revenue officer",
    "head of growth",
    "vp growth",
    "vp of growth",
    "vp of marketing",
    "gtm engineer",
    "director of demand gen",
    "director of demand generation",
    "chief revenue",
)

GENERIC_SAAS_INDUSTRIES = ("b2b saas", "developer tools", "ai & data infrastructure", "ai infrastructure")

FUNDING_SIGNAL_MARKERS = ("funding", "fund", "series a", "series b", "raised", "venture")
LINKEDIN_ENGAGER_MARKERS = ("linkedin", "thought leadership", "social selling")

LOW_EVIDENCE_NOTE = (
    "We could not generate a reliable ICP from this URL. This usually happens when the "
    "page is a login wall or is protected by an anti-bot filter like Cloudflare. "
    "Try a public marketing / about URL, or paste a one-sentence product blurb."
)

RICH_TEXT_CHARS = 280
THIN_TEXT_CHARS = 160


@dataclass
class PageEvidence:
    url: str
    title: str = ""
    meta_description: str = ""
    og: dict[str, str] = field(default_factory=dict)
    json_ld: list[dict[str, Any]] = field(default_factory=list)
    html_lang: str = ""
    manifest: dict[str, Any] = field(default_factory=dict)
    visible_text: str = ""
    h1: str = ""
    has_password_field: bool = False
    has_login_copy: bool = False
    has_indic_script: bool = False

    @property
    def brand_text(self) -> str:
        parts = [
            self.title,
            self.og.get("og:title", ""),
            self.og.get("og:site_name", ""),
            str(self.manifest.get("name") or ""),
            str(self.manifest.get("short_name") or ""),
        ]
        for obj in self.json_ld:
            name = obj.get("name")
            if name:
                parts.append(str(name))
        return _WS_RE.sub(" ", " ".join(p for p in parts if p)).strip()

    @property
    def descriptive_text(self) -> str:
        parts = [
            self.title,
            self.meta_description,
            self.og.get("og:title", ""),
            self.og.get("og:description", ""),
            self.h1,
            str(self.manifest.get("description") or ""),
            self.visible_text,
        ]
        for obj in self.json_ld:
            for key in ("name", "description", "headline", "applicationCategory"):
                val = obj.get(key)
                if val:
                    parts.append(str(val))
        return _WS_RE.sub(" ", " ".join(p for p in parts if p)).strip()


@dataclass
class SiteEvidence:
    url: str
    pages: list[PageEvidence] = field(default_factory=list)
    paths_fetched: list[str] = field(default_factory=list)
    product_blurb: str = ""

    @property
    def primary(self) -> PageEvidence:
        return self.pages[0] if self.pages else PageEvidence(url=self.url)

    @property
    def combined_text(self) -> str:
        chunks = [self.product_blurb] if self.product_blurb else []
        for page in self.pages:
            chunks.append(page.descriptive_text)
        return _WS_RE.sub(" ", " ".join(c for c in chunks if c)).strip()

    @property
    def is_login_gated(self) -> bool:
        home = self.primary
        return bool(home.has_password_field or home.has_login_copy)

    @property
    def visible_char_count(self) -> int:
        return len(self.combined_text)

    @property
    def richness(self) -> str:
        """empty | thin | rich — based on crawled evidence, not the brand."""
        text = self.combined_text
        if len(text) < 24 and not self.primary.title:
            return "empty"
        if self.product_blurb.strip() and len(self.product_blurb.strip()) >= 24:
            return "rich"
        if self.is_login_gated and len(text) < RICH_TEXT_CHARS:
            return "thin"
        if len(text) < THIN_TEXT_CHARS:
            return "thin" if text or self.primary.title else "empty"
        return "rich"

    def evidence_blob(self) -> str:
        """Compact, structured evidence for the LLM — not a marketing guess."""
        home = self.primary
        og_bits = [f"{k}={v}" for k, v in home.og.items() if v]
        json_ld_names = []
        for obj in home.json_ld:
            label = obj.get("@type") or obj.get("type") or "Thing"
            name = obj.get("name") or obj.get("headline") or ""
            desc = obj.get("description") or ""
            json_ld_names.append(f"{label}: {name} {desc}".strip())
        lines = [
            f"url: {self.url}",
            f"paths_fetched: {', '.join(self.paths_fetched) or '(homepage only)'}",
            f"html_lang: {home.html_lang or 'unknown'}",
            f"title: {home.title or '(none)'}",
            f"meta_description: {home.meta_description or '(none)'}",
            f"og: {'; '.join(og_bits) or '(none)'}",
            f"json_ld: {'; '.join(json_ld_names) or '(none)'}",
            f"manifest: {home.manifest or '{}'}",
            f"login_gated: {self.is_login_gated}",
            f"richness: {self.richness}",
            f"indic_script: {home.has_indic_script}",
            f"visible_copy: {self.combined_text[:4000] or '(none)'}",
        ]
        if self.product_blurb:
            lines.append(f"operator_blurb: {self.product_blurb.strip()[:800]}")
        return "\n".join(lines)


def _attr(tag: str, name: str) -> str:
    match = re.search(
        rf'''(?:^|\s){re.escape(name)}\s*=\s*["']([^"']+)["']''',
        tag,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _visible_text(html: str, *, max_chars: int = 6000) -> str:
    raw = _SCRIPT_STYLE_RE.sub(" ", html or "")
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", raw)).strip()
    return text[:max_chars]


def _extract_json_ld(html: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for match in re.finditer(
        r'''<script[^>]*type=["']application/ld\+json["'][^>]*>(.*?)</script>''',
        html or "",
        re.IGNORECASE | re.DOTALL,
    ):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        if isinstance(parsed, dict):
            graph = parsed.get("@graph")
            if isinstance(graph, list):
                objects.extend(x for x in graph if isinstance(x, dict))
            else:
                objects.append(parsed)
        elif isinstance(parsed, list):
            objects.extend(x for x in parsed if isinstance(x, dict))
    return objects


def extract_page_evidence(html: str, *, url: str = "") -> PageEvidence:
    """Parse one HTML document into structured evidence. Pure; no network."""
    html = html or ""
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = _WS_RE.sub(" ", title_m.group(1)).strip() if title_m else ""
    lang_m = re.search(r"<html[^>]*\slang=['\"]([^'\"]+)['\"]", html, re.IGNORECASE)
    html_lang = (lang_m.group(1).strip() if lang_m else "")[:16]

    og: dict[str, str] = {}
    meta_description = ""
    for tag in re.findall(r"<meta\b[^>]*>", html, re.IGNORECASE):
        prop = (_attr(tag, "property") or _attr(tag, "name") or "").lower()
        content = _attr(tag, "content")
        if not prop or not content:
            continue
        if prop in {"description", "twitter:description"} and not meta_description:
            meta_description = content
        if prop.startswith("og:") or prop.startswith("twitter:"):
            og[prop] = content
        if prop == "og:description" and not meta_description:
            meta_description = content

    visible = _visible_text(html)
    h1_m = _H1_RE.search(html)
    h1 = _WS_RE.sub(" ", _TAG_RE.sub(" ", h1_m.group(1))).strip()[:200] if h1_m else ""
    lowered = f"{title} {h1} {visible}".lower()
    return PageEvidence(
        url=url,
        title=title,
        meta_description=meta_description,
        og=og,
        json_ld=_extract_json_ld(html),
        html_lang=html_lang,
        visible_text=visible,
        h1=h1,
        has_password_field=bool(re.search(r'''type=["']password["']''', html, re.I)),
        has_login_copy=bool(re.search(r"\b(log\s*in|sign\s*in|sign-in|password)\b", lowered)),
        has_indic_script=bool(_DEVANAGARI_RE.search(html)),
    )


def _origin(url: str) -> str:
    parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
    netloc = parsed.netloc or parsed.path.split("/")[0]
    return f"{scheme}://{netloc}"


def _join(url: str, path: str) -> str:
    return urllib.parse.urljoin(_origin(url).rstrip("/") + "/", path.lstrip("/"))


def fetch_url_body(url: str, *, timeout: int = 12, max_bytes: int = 2_000_000) -> str:
    """Fetch a URL body. Returns '' on any failure (never raises)."""
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    from engine.llm.website_intake import is_safe_fetch_url

    if not is_safe_fetch_url(url):
        return ""
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AttainlyOnboardingBot/1.0",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            raw = resp.read(max_bytes).decode("utf-8", errors="ignore")
        return raw
    except Exception:
        return ""


def _parse_manifest(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    keep = {k: data[k] for k in ("name", "short_name", "description", "lang") if data.get(k)}
    return keep


def collect_website_evidence(
    url: str,
    *,
    homepage_html: Optional[str] = None,
    product_blurb: str = "",
    extra_bodies: Optional[dict[str, str]] = None,
    fetch_extras: bool = True,
) -> SiteEvidence:
    """Crawl homepage + extra paths and return structured evidence."""
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    site = SiteEvidence(url=url or "", product_blurb=product_blurb or "")
    html = homepage_html if homepage_html is not None else fetch_url_body(url)
    home = extract_page_evidence(html, url=url)
    extras = extra_bodies or {}

    firecrawl_md = ""
    if homepage_html is None and url:
        try:
            from engine.integrations.firecrawl_client import FirecrawlClient

            client = FirecrawlClient()
            if client.has_api_key:
                firecrawl_md = client.scrape_markdown(url, max_chars=8000)
        except Exception:
            firecrawl_md = ""
    if firecrawl_md.strip():
        home.visible_text = _WS_RE.sub(
            " ",
            f"{home.visible_text} {firecrawl_md.strip()}".strip(),
        )[:8000]

    site.pages.append(home)
    site.paths_fetched.append(url or "/")

    if fetch_extras and url and homepage_html is None:
        for path in EXTRA_PATHS:
            extra_url = _join(url, path)
            if extra_url.rstrip("/") == (url or "").rstrip("/"):
                continue
            raw = extras.get(path)
            if raw is None:
                raw = fetch_url_body(extra_url, timeout=5, max_bytes=400_000)
            if not raw:
                continue
            site.paths_fetched.append(extra_url)
            if path.endswith("manifest.json"):
                home.manifest = _parse_manifest(raw)
                continue
            site.pages.append(extract_page_evidence(raw, url=extra_url))
    elif extras:
        for path, raw in extras.items():
            extra_url = _join(url, path) if url else path
            site.paths_fetched.append(extra_url)
            if path.endswith("manifest.json"):
                home.manifest = _parse_manifest(raw)
            elif raw:
                site.pages.append(extract_page_evidence(raw, url=extra_url))

    return site



def _norm(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").lower()).strip()


def page_mentions(evidence: SiteEvidence, phrases: tuple[str, ...] | list[str]) -> bool:
    blob = _norm(evidence.combined_text)
    return any(_norm(p) in blob for p in phrases if p)


# Observed Gojiberry UI defaults on /organization-creation (chunk-IKMU54LD.js):
# signalOptions preselected: top-5-active, recent-job-changes.
# NOT preselected: recent-funding, companies-hiring.
# These are UI defaults, not website-derived recommendations.
GOJIBERRY_EVENT_SIGNAL_DEFAULTS: tuple[dict[str, Any], ...] = (
    {
        "type": "RECENT_ACTIVITY",
        "value": "true",
        "label": "Top 5% active profiles in your ICP",
        "name": "Top 5% active profiles in your ICP",
        "reasoning": "Gojiberry onboarding preselects RECENT_ACTIVITY. Not inferred from the website.",
        "enabled": True,
        "source": "ui_default",
        "intent_points": 2,
        "weight": 2,
        "heat": "Warm",
    },
    {
        "type": "RECENTLY_CHANGED_JOB",
        "value": "true",
        "label": "Recent job changes (< 90 days)",
        "name": "Recent job changes (< 90 days)",
        "reasoning": "Gojiberry onboarding preselects RECENTLY_CHANGED_JOB. Not inferred from the website.",
        "enabled": True,
        "source": "ui_default",
        "intent_points": 3,
        "weight": 3,
        "heat": "Hot",
    },
    {
        "type": "RECENT_FUNDING_EVENT",
        "value": "true",
        "label": "Companies that have recently raised funds",
        "name": "Companies that have recently raised funds",
        "reasoning": "Gojiberry onboarding leaves funding OFF unless the operator enables it.",
        "enabled": False,
        "source": "ui_default",
        "intent_points": 3,
        "weight": 3,
        "heat": "Hot",
    },
    {
        "type": "HIRING",
        "value": "true",
        "label": "Companies hiring right now",
        "name": "Companies hiring right now",
        "reasoning": "Gojiberry onboarding leaves hiring OFF unless the operator enables it.",
        "enabled": False,
        "source": "ui_default",
        "intent_points": 2,
        "weight": 2,
        "heat": "Hot",
    },
)

_KEYWORD_STOP = {
    "about", "home", "login", "signin", "sign", "password", "welcome", "official",
    "website", "page", "pages", "click", "learn", "more", "free", "best", "simple",
    "online", "your", "you", "our", "the", "and", "for", "with", "from", "this",
    "that", "they", "their", "www", "http", "https", "com", "app", "apps",
    "software", "platform", "solution", "solutions", "system", "service", "services",
    "company", "inc", "llc", "ltd", "copyright", "privacy", "terms", "cookie",
    "cookies", "help", "support", "contact", "shop", "store", "buy", "cart",
    "account", "email", "phone", "skip", "menu", "search",
}

_GENERIC_AUDIENCE = {
    "you", "your", "yourself", "consumers", "consumer", "customers", "customer",
    "users", "user", "people", "everyone", "anyone", "somebody", "someone",
    "millions", "businesses", "companies", "teams", "world",
}


def _company_name_from_evidence(evidence: SiteEvidence, url: str) -> str:
    home = evidence.primary
    for candidate in (
        home.og.get("og:site_name"),
        home.manifest.get("short_name"),
        home.manifest.get("name"),
    ):
        if candidate and str(candidate).strip():
            return str(candidate).strip()[:80]
    for obj in home.json_ld:
        name = obj.get("name")
        if name and str(name).strip():
            return str(name).strip()[:80]
    title = home.title.strip()
    if title:
        return re.split(r"\s+[\|\-–—:]\s+", title)[0].strip()[:80]
    host = urllib.parse.urlparse(url if "://" in url else f"https://{url}").hostname or url
    host = (host or "").lstrip("www.")
    return host.split(".")[0].capitalize() if host else "Your company"


def _locations_from_evidence(evidence: SiteEvidence) -> list[str]:
    """Only emit a location when the page copy or html lang actually names one."""
    home = evidence.primary
    found: list[str] = []
    blob = _norm(evidence.combined_text)
    mapping = (
        ("united states", "United States"),
        ("united kingdom", "United Kingdom"),
        ("canada", "Canada"),
        ("india", "India"),
        ("germany", "Germany"),
        ("australia", "Australia"),
        ("singapore", "Singapore"),
        ("france", "France"),
    )
    for needle, label in mapping:
        if needle in blob:
            found.append(label)
    lang = (home.html_lang or "").lower()
    # html lang alone is not a buyer geo. Only add India when Indic script is on-page
    # AND no other location was named — still an inference, kept empty by default.
    if not found and home.has_indic_script and ("india" in blob or lang.startswith("hi")):
        found.append("India")
    return found[:4]


def _industries_from_json_ld(evidence: SiteEvidence) -> list[str]:
    out: list[str] = []
    for page in evidence.pages:
        for obj in page.json_ld:
            for key in ("applicationCategory", "industry", "knowsAbout"):
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    out.append(val.strip()[:80])
                elif isinstance(val, list):
                    out.extend(str(x).strip()[:80] for x in val if str(x).strip())
    # de-dupe preserve order
    seen: set[str] = set()
    unique: list[str] = []
    for item in out:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:6]


def _description_from_evidence(evidence: SiteEvidence) -> str:
    home = evidence.primary
    for candidate in (
        evidence.product_blurb.strip(),
        home.meta_description,
        home.og.get("og:description", ""),
        home.h1,
        str(home.manifest.get("description") or ""),
    ):
        if candidate and str(candidate).strip() and len(str(candidate).strip()) >= 12:
            return str(candidate).strip()[:400]
    return ""


def extract_search_keywords(evidence: SiteEvidence, *, company_name: str = "") -> list[str]:
    """1–3 word phrases from title/h1/meta — Gojiberry search_keywords, not a funding pack."""
    home = evidence.primary
    brand = _norm(company_name or _company_name_from_evidence(evidence, evidence.url))
    sources = [
        home.title,
        home.h1,
        home.meta_description,
        home.og.get("og:title", ""),
        home.og.get("og:description", ""),
        evidence.product_blurb,
    ]
    for obj in home.json_ld:
        for key in ("name", "headline", "description", "applicationCategory"):
            if obj.get(key):
                sources.append(str(obj.get(key)))

    phrases: list[str] = []
    seen: set[str] = set()

    def _keep(phrase: str) -> None:
        cleaned = _WS_RE.sub(" ", phrase).strip(" .,;:/-")
        if not cleaned:
            return
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9+-]{1,}", cleaned) if w]
        if not 1 <= len(words) <= 3:
            return
        if any(len(w) > 28 for w in words):
            return
        lowered = " ".join(w.lower() for w in words)
        if lowered in seen or lowered == brand or lowered in _KEYWORD_STOP:
            return
        if all(w.lower() in _KEYWORD_STOP or w.lower() in _GENERIC_AUDIENCE for w in words):
            return
        if all(w.lower() in brand.split() for w in words):
            return
        seen.add(lowered)
        phrases.append(" ".join(words))

    for src in sources:
        raw = _WS_RE.sub(" ", src or "").strip()
        if not raw:
            continue
        # Prefer the clause after a dash/pipe in titles: "Brand — invoicing for shops"
        parts = re.split(r"\s+[\|\-–—:]\s+", raw)
        for part in parts[1:] or parts:
            _keep(part)
        for word in re.findall(r"[A-Za-z][A-Za-z0-9+-]{3,}", raw):
            if word.lower() not in _KEYWORD_STOP and word.lower() not in _GENERIC_AUDIENCE:
                _keep(word)
        # two-word windows excluding stopwords
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", raw)
        for i in range(len(tokens) - 1):
            a, b = tokens[i], tokens[i + 1]
            if a.lower() in _KEYWORD_STOP or b.lower() in _KEYWORD_STOP:
                continue
            _keep(f"{a} {b}")

    return phrases[:8]


def signals_from_search_keywords(keywords: list[str]) -> list[dict[str, Any]]:
    """Map search_keywords to AgentVariableV2Dto SEARCH_KEYWORD rows (Gojiberry client wraps quotes)."""
    out: list[dict[str, Any]] = []
    for kw in keywords:
        text = str(kw).strip().strip('"')
        if not text:
            continue
        quoted = f'"{text}"'
        out.append(
            {
                "type": "SEARCH_KEYWORD",
                "value": quoted,
                "label": f"LinkedIn keyword: {text}",
                "name": text,
                "reasoning": "Extracted from on-page product language. Gojiberry turns search_keywords into SEARCH_KEYWORD variables.",
                "enabled": True,
                "source": "website",
                "intent_points": 2,
                "weight": 2,
                "heat": "Warm",
            }
        )
    return out


def title_is_generic_saas(title: str) -> bool:
    lowered = (title or "").strip().lower()
    return any(marker == lowered or marker in lowered for marker in GENERIC_SAAS_TITLES)


def _empty_icp(name: str, *, summary: str = "", offer: str = "", locations: list[str] | None = None,
               need: str = LOW_EVIDENCE_NOTE, status: str = "low_evidence", product_type: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "company_name": name,
        "companyName": name,
        "summary": summary,
        "description": summary,
        "offer": offer,
        "industry": "",
        "icp_description": "",
        "client_cure": "",
        "pain_points": [],
        "pains": "",
        "key_features": [],
        "keyFeatures": [],
        "social_proof": [],
        "socialProof": [],
        "target_job_titles": [],
        "job_titles": [],
        "adjacent_job_titles": [],
        "adjacentJobTitles": [],
        "target_industries": [],
        "industries": [],
        "target_company_sizes": [],
        "company_sizes": [],
        "target_locations": list(locations or []),
        "countries": list(locations or []),
        "target_company_types": [],
        "company_types": [],
        "competitors": [],
        "search_keywords": [],
        "recommended_signals": [],
        "suggested_signal_types": [],
        "need_more_input": need,
        "product_type": product_type,
    }


_FOR_AUDIENCE_RE = re.compile(
    r"(?:software|platform|app|tool|system|service|solution|product)s?\s+for\s+([A-Za-z][A-Za-z0-9 &/,-]{2,48})",
    re.IGNORECASE,
)
_BUILT_FOR_RE = re.compile(
    r"(?:built|designed|made|created|intended)\s+for\s+([A-Za-z][A-Za-z0-9 &/,-]{2,60})",
    re.IGNORECASE,
)
_HELP_AUDIENCE_RE = re.compile(
    r"(?:we|our (?:product|platform|app|software)|this (?:product|platform|app|software))\s+helps?\s+([A-Za-z][A-Za-z0-9 &/,-]{2,48})\s+(?:to|with|who|send|run|manage|track|collect|reach|book|close)",
    re.IGNORECASE,
)
_NAMED_ROLE_RE = re.compile(
    r"\b("
    r"(?:shop|store|clinic|hospital|restaurant|agency|practice|warehouse|salon|hotel|school|farm)\s+owners?"
    r"|(?:hr|sales|marketing|product|engineering|finance|operations|recruiting|revenue|clinic|hospital)\s+"
    r"(?:managers?|directors?|leads?|heads?)"
    r"|founders?|co-founders?|developers?|engineers?|recruiters?|clinicians?|practitioners?"
    r"|merchants?|retailers?|shopkeepers?"
    r"|heads? of [a-z]{3,24}"
    r"|vps? of [a-z]{3,24}"
    r")\b",
    re.IGNORECASE,
)
_COMPETITOR_RE = re.compile(
    r"(?:unlike|versus|vs\.?|alternative to|instead of|compared to)\s+([A-Za-z][A-Za-z0-9.&-]{1,40})",
    re.IGNORECASE,
)
_OPERATOR_NOUNS = {
    "shop", "store", "retailer", "clinic", "hospital", "restaurant", "agency",
    "practice", "merchant", "vendor", "pharmacy", "warehouse", "salon", "hotel",
    "school", "farm", "gym", "studio", "workshop", "dealership",
}
_DEPT_NOUNS = {
    "sales", "marketing", "finance", "operations", "hr", "recruiting", "product",
    "engineering", "support", "success", "revenue", "clinic", "hospital",
}
CONSUMER_MARKETPLACE_MARKERS = (
    "online marketplace", "online shopping", "add to cart", "shop from",
    "millions of products", "thousands of sellers", "great prices", "fast delivery",
    "deals of the day", "buy now", "we help you shop", "shop online",
)
B2B_PRODUCT_MARKERS = (
    "software", "platform", "saas", "for teams", "for businesses", "api",
    "dashboard", "workflow", "automation", "b2b", "for shops", "for clinics",
    "for hospitals", "for agencies", "for retailers",
)


def _signal(type_: str, label: str, reasoning: str, value: str, *, heat: str = "Hot") -> dict[str, Any]:
    return {
        "type": type_,
        "name": label,
        "label": label,
        "reasoning": reasoning,
        "value": value,
        "intent_points": 3 if heat == "Hot" else 2,
        "weight": 3 if heat == "Hot" else 2,
        "heat": heat,
        "source": "website",
        "enabled": True,
    }


def _singular_noun(word: str) -> str:
    token = (word or "").strip().lower()
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith(("sses", "ches", "shes", "xes")):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def _title_case_role(phrase: str) -> str:
    words = _WS_RE.sub(" ", phrase).strip().split()
    small = {"of", "and", "the", "for"}
    out = []
    for i, word in enumerate(words):
        low = word.lower()
        if low in {"hr", "vp", "cfo", "cto", "ceo", "cro", "gtm"}:
            out.append(low.upper())
        elif i > 0 and low in small:
            out.append(low)
        else:
            out.append(word[:1].upper() + word[1:].lower())
    return " ".join(out)


def _cut_who_clause(phrase: str) -> str:
    return re.split(r"\bwho\b", phrase, maxsplit=1, flags=re.I)[0].strip(" .,;:-")


def audience_to_role_types(phrase: str) -> list[str]:
    """Turn a marketing audience phrase into buyer role types.

    Inference, not a SaaS exec pack: "independent shops" → Independent Shop Owner,
    "sales teams" → Sales Manager. Generic you/consumers/businesses → empty.
    """
    cleaned = _cut_who_clause(_WS_RE.sub(" ", phrase or "").strip(" .,;:-"))
    lowered = cleaned.lower()
    if not lowered or lowered in _GENERIC_AUDIENCE:
        return []
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9+-]*", lowered) if w]
    if not words:
        return []
    if words[0] in _GENERIC_AUDIENCE and len(words) <= 2:
        return []
    if all(w in _GENERIC_AUDIENCE or w in _KEYWORD_STOP for w in words):
        return []

    if any(w in {"owner", "owners", "manager", "managers", "director", "directors",
                 "founder", "founders", "developer", "developers", "engineer", "engineers",
                 "recruiter", "recruiters", "lead", "leads", "head", "heads",
                 "retailer", "retailers", "merchant", "merchants", "shopkeeper", "shopkeepers"}
           for w in words):
        singular = [_singular_noun(w) if w not in {"of", "and", "the"} else w for w in words]
        role = _title_case_role(" ".join(singular))
        return [role] if role and not title_is_generic_saas(role) else []

    last = _singular_noun(words[-1])
    if last in _OPERATOR_NOUNS:
        adj = " ".join(words[:-1]).strip()
        adj = " ".join(w for w in adj.split() if w not in _GENERIC_AUDIENCE)
        label = f"{adj} {last} owner".strip() if adj else f"{last} owner"
        role = _title_case_role(label)
        return [role] if role and not title_is_generic_saas(role) else []

    if last in {"team", "teams"} and len(words) >= 2:
        dept = " ".join(words[:-1]).strip()
        if not dept or dept in _GENERIC_AUDIENCE:
            return []
        dept_last = dept.split()[-1]
        if dept_last in _DEPT_NOUNS or dept_last not in _GENERIC_AUDIENCE:
            role = _title_case_role(f"{dept} manager")
            if role and not title_is_generic_saas(role):
                return [role]
        return []
    return []


def classify_site(evidence: SiteEvidence) -> str:
    """b2b_product | consumer_marketplace | app_login | thin | marketing_site."""
    blob = _norm(evidence.combined_text)
    if evidence.is_login_gated and evidence.richness in {"thin", "empty"}:
        return "app_login"
    consumer_hits = sum(1 for marker in CONSUMER_MARKETPLACE_MARKERS if marker in blob)
    b2b_hits = sum(1 for marker in B2B_PRODUCT_MARKERS if marker in blob)
    has_for_software = bool(_FOR_AUDIENCE_RE.search(evidence.combined_text or ""))
    has_built_for = bool(_BUILT_FOR_RE.search(evidence.combined_text or ""))
    if consumer_hits >= 2 and not has_for_software and b2b_hits <= 1:
        return "consumer_marketplace"
    if evidence.richness in {"thin", "empty"} and not evidence.product_blurb.strip():
        return "thin"
    if has_for_software or has_built_for or b2b_hits >= 2:
        return "b2b_product"
    if evidence.richness == "rich":
        return "marketing_site"
    return "thin"


def extract_named_roles(text: str) -> list[str]:
    roles: list[str] = []
    seen: set[str] = set()
    for match in _NAMED_ROLE_RE.finditer(text or ""):
        for role in audience_to_role_types(match.group(1)):
            key = role.lower()
            if key not in seen and not title_is_generic_saas(role):
                seen.add(key)
                roles.append(role)
    return roles[:8]


def extract_audience_roles(text: str) -> list[str]:
    roles: list[str] = []
    seen: set[str] = set()
    for regex in (_BUILT_FOR_RE, _FOR_AUDIENCE_RE, _HELP_AUDIENCE_RE):
        for match in regex.finditer(text or ""):
            for role in audience_to_role_types(match.group(1)):
                key = role.lower()
                if key not in seen:
                    seen.add(key)
                    roles.append(role)
    return roles[:8]


def extract_key_features(evidence: SiteEvidence) -> list[str]:
    home = evidence.primary
    features: list[str] = []
    blob = evidence.combined_text or ""
    if home.h1 and 12 <= len(home.h1) <= 80:
        features.append(_WS_RE.sub(" ", home.h1).strip())
    for chunk in re.split(r"(?<=[.!?])\s+|,\s+and\s+|;\s+", blob):
        piece = _WS_RE.sub(" ", chunk).strip(" .")
        if not piece or len(piece) < 18 or len(piece) > 90:
            continue
        if re.match(r"^(create|track|send|collect|automate|manage|book|reach|analyze)\b", piece, re.I):
            features.append(piece)
        if len(features) >= 5:
            break
    seen: set[str] = set()
    unique: list[str] = []
    for item in features:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:5]


def extract_pains(evidence: SiteEvidence) -> list[str]:
    pains: list[str] = []
    blob = evidence.combined_text or ""
    for match in re.finditer(
        r"(?:without|stop|no more|don't want|do not want)\s+([^.!?]{8,70})",
        blob,
        re.IGNORECASE,
    ):
        pains.append(_WS_RE.sub(" ", match.group(0)).strip(" ."))
    return pains[:4]


def extract_competitors(evidence: SiteEvidence) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for match in _COMPETITOR_RE.finditer(evidence.combined_text or ""):
        name = _WS_RE.sub(" ", match.group(1)).strip(" .,")
        if not name or name.lower() in _GENERIC_AUDIENCE:
            continue
        key = name.lower()
        if key not in seen:
            seen.add(key)
            names.append(name)
    return names[:8]


def buyers_from_copy(evidence: SiteEvidence) -> dict[str, Any]:
    """Infer buyer *role types* from marketing language; never a fixed SaaS exec list.

    Observation (Gojiberry client): generate-icp-from-website maps job_titles as
    returned; empty stays empty. Inference (Attainly): when the page names an
    audience ("for independent shops", "built for shop owners", "for sales teams")
    turn that into a role type. Consumer marketplace / login walls stay empty.
    """
    product_type = classify_site(evidence)
    blob = evidence.combined_text or ""
    if product_type in {"app_login", "thin"} and not evidence.product_blurb.strip():
        return {
            "titles": [],
            "industries": [],
            "offer": "",
            "signals": [],
            "product_type": product_type,
            "legacy": [],
            "features": [],
            "pains": [],
            "competitors": [],
        }
    if product_type == "consumer_marketplace" and not evidence.product_blurb.strip():
        return {
            "titles": [],
            "industries": list(_industries_from_json_ld(evidence)),
            "offer": "",
            "signals": [],
            "product_type": product_type,
            "legacy": [],
            "features": extract_key_features(evidence),
            "pains": extract_pains(evidence),
            "competitors": extract_competitors(evidence),
        }

    titles: list[str] = []
    seen: set[str] = set()
    for role in extract_named_roles(blob) + extract_audience_roles(blob):
        if title_is_generic_saas(role) and not page_mentions(evidence, (role,)):
            continue
        key = role.lower()
        if key not in seen:
            seen.add(key)
            titles.append(role)

    industries = list(_industries_from_json_ld(evidence))
    offer = _description_from_evidence(evidence)
    return {
        "titles": titles[:8],
        "industries": industries,
        "offer": offer,
        "signals": [],
        "product_type": product_type,
        "legacy": ["search_keyword"],
        "features": extract_key_features(evidence),
        "pains": extract_pains(evidence),
        "competitors": extract_competitors(evidence),
    }


def infer_icp_from_evidence(evidence: SiteEvidence) -> dict[str, Any]:
    """ICP from crawled evidence only. Never invent a SaaS executive pack."""
    richness = evidence.richness
    name = _company_name_from_evidence(evidence, evidence.url)
    locations = _locations_from_evidence(evidence)
    summary = _description_from_evidence(evidence)
    json_ld_industries = _industries_from_json_ld(evidence)
    keywords = extract_search_keywords(evidence, company_name=name)[:10]
    buyers = buyers_from_copy(evidence)
    product_type = str(buyers["product_type"] or classify_site(evidence))

    if richness == "empty" and not evidence.product_blurb.strip():
        return _empty_icp(name, locations=locations, product_type=product_type or "thin")

    if product_type in {"app_login", "thin"} and not buyers["titles"] and not evidence.product_blurb.strip():
        empty = _empty_icp(
            name,
            summary=summary or evidence.primary.title,
            offer="",
            locations=locations,
            product_type=product_type,
        )
        empty["search_keywords"] = []
        empty["recommended_signals"] = []
        return empty

    titles = list(buyers["titles"])
    industries = list(buyers["industries"] or json_ld_industries)
    offer = buyers["offer"] or summary
    keywords = keywords[:10]
    signals = list(buyers["signals"]) or signals_from_search_keywords(keywords)
    features = list(buyers.get("features") or [])
    pains = list(buyers.get("pains") or [])
    competitors = list(buyers.get("competitors") or [])
    status = "ok"
    note = ""
    if product_type == "consumer_marketplace" and not titles:
        note = (
            "This reads as a consumer or marketplace site. Pitch and keywords come from "
            "the page; buyer job titles were left empty so a sales ICP is not invented. "
            "Edit titles or add a product blurb if you sell to a business buyer."
        )
    elif product_type in {"app_login", "thin"} and titles:
        note = (
            "Inferred only from the login/app title and on-page copy. "
            "Add a marketing URL or product blurb if you want a richer ICP."
        )
    elif not titles:
        note = (
            "Pitch extracted from the page. Buyer titles were not named on-site — "
            "role types were not inferred from a specific audience. Add a blurb or edit titles."
        )
        if richness != "rich" and not evidence.product_blurb.strip():
            status = "low_evidence"
            note = LOW_EVIDENCE_NOTE

    result = _empty_icp(
        name,
        summary=summary or offer,
        offer=offer,
        locations=locations,
        need=note,
        status=status,
        product_type=product_type,
    )
    result["target_job_titles"] = titles
    result["job_titles"] = titles
    result["target_industries"] = industries
    result["industries"] = industries
    result["search_keywords"] = keywords
    result["recommended_signals"] = signals
    result["suggested_signal_types"] = list(buyers["legacy"] or (["search_keyword"] if keywords else []))
    result["industry"] = industries[0] if industries else ""
    result["key_features"] = features
    result["keyFeatures"] = features
    result["pain_points"] = pains
    result["pains"] = "; ".join(pains)
    result["competitors"] = competitors
    result["icp_description"] = (
        f"{', '.join(titles)} at {', '.join(industries).lower()} organizations" if titles and industries
        else (", ".join(titles) if titles else "")
    )
    result["client_cure"] = offer
    result["need_more_input"] = note
    return result


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = str(item).strip() if item is not None else ""
        if s:
            out.append(s)
    return out


def sanitize_llm_icp(draft: dict[str, Any], evidence: SiteEvidence) -> dict[str, Any]:
    """Keep LLM fields that the page can support; never refill a SaaS exec pack."""
    inferred = infer_icp_from_evidence(evidence)
    blob = _norm(evidence.combined_text + " " + evidence.product_blurb)

    product_type = str(inferred.get("product_type") or classify_site(evidence))
    titles = _as_str_list(draft.get("job_titles") or draft.get("target_job_titles"))
    kept_titles: list[str] = []
    for title in titles:
        if title_is_generic_saas(title) and not page_mentions(evidence, (title,)):
            continue
        if product_type in {"consumer_marketplace", "app_login"} and not page_mentions(evidence, (title,)):
            continue
        kept_titles.append(title)
    if not kept_titles:
        kept_titles = [
            t for t in _as_str_list(inferred.get("job_titles"))
            if not title_is_generic_saas(t) or page_mentions(evidence, (t,))
        ]
    if product_type in {"consumer_marketplace", "app_login"} and not evidence.product_blurb.strip():
        kept_titles = [t for t in kept_titles if page_mentions(evidence, (t,))]
    industries = _as_str_list(draft.get("industries") or draft.get("target_industries"))
    industries = [
        ind
        for ind in industries
        if _norm(ind) not in GENERIC_SAAS_INDUSTRIES or _norm(ind) in blob
    ]
    if not industries:
        industries = list(inferred.get("industries") or [])

    sizes = _as_str_list(draft.get("company_sizes") or draft.get("target_company_sizes"))
    countries = _as_str_list(draft.get("countries") or draft.get("target_locations"))
    if not countries:
        countries = list(inferred.get("countries") or [])
    company_types = _as_str_list(draft.get("company_types") or draft.get("target_company_types"))
    competitors = _as_str_list(draft.get("competitors") or draft.get("excludedCompanies"))
    if not competitors:
        competitors = list(inferred.get("competitors") or [])
    keywords = _as_str_list(draft.get("search_keywords"))[:10]
    if not keywords:
        keywords = list(inferred.get("search_keywords") or [])[:10]

    rec = [dict(s) for s in (draft.get("recommended_signals") or []) if isinstance(s, dict)]
    allow_funding = any(m in blob for m in FUNDING_SIGNAL_MARKERS)
    allow_li = any(m in blob for m in LINKEDIN_ENGAGER_MARKERS)
    cleaned_rec: list[dict[str, Any]] = []
    for sig in rec:
        kind = str(sig.get("type") or sig.get("name") or "").lower()
        label = str(sig.get("label") or sig.get("name") or "").lower()
        if ("fund" in kind or "fund" in label) and not allow_funding:
            continue
        if ("linkedin" in kind or "linkedin" in label) and "keyword" not in kind and "keyword" not in label and not allow_li:
            continue
        if str(sig.get("type") or "").upper() in {"LOOKALIKE", "WEBSITE_VISITOR"}:
            # Gojiberry: LOOKALIKE / WEBSITE_VISITOR are agentType, not variables[] from the site.
            continue
        cleaned_rec.append(sig)
    keyword_signals = signals_from_search_keywords(keywords)
    if not cleaned_rec:
        cleaned_rec = keyword_signals
    else:
        have_kw = any(str(s.get("type") or "").upper() == "SEARCH_KEYWORD" for s in cleaned_rec)
        if not have_kw:
            cleaned_rec = keyword_signals + cleaned_rec

    offer = str(draft.get("offer") or draft.get("description") or inferred.get("offer") or "")
    if re.search(r"growth and prosperity", offer, re.I) and "prosperity" not in blob:
        offer = str(inferred.get("offer") or "")
    summary = str(draft.get("summary") or draft.get("description") or inferred.get("summary") or "")
    if re.search(r"growth and prosperity", summary, re.I) and "prosperity" not in blob:
        summary = str(inferred.get("summary") or "")

    status = str(draft.get("status") or inferred.get("status") or "ok")
    if evidence.richness == "empty" and not evidence.product_blurb.strip():
        status = "low_evidence"
        kept_titles = []
        cleaned_rec = []
        keywords = []
    if product_type in {"app_login", "thin"} and not kept_titles and not evidence.product_blurb.strip():
        status = "low_evidence"
        kept_titles = []
        cleaned_rec = []
        keywords = []
    elif product_type == "consumer_marketplace" and not evidence.product_blurb.strip():
        kept_titles = [t for t in kept_titles if page_mentions(evidence, (t,))]
        if status == "low_evidence" and (summary or offer):
            status = "ok"

    need = str(draft.get("need_more_input") or inferred.get("need_more_input") or "")
    if status == "low_evidence" and not need:
        need = LOW_EVIDENCE_NOTE
    if status != "low_evidence" and not kept_titles and not need:
        need = (
            "Pitch extracted from the page. Buyer titles were not named on-site — "
            "add a one-sentence product blurb or edit titles before launch."
        )

    name = str(draft.get("company_name") or draft.get("companyName") or inferred.get("company_name") or "")
    pains_list = _as_str_list(draft.get("pain_points"))
    pains_text = str(draft.get("pains") or "").strip()
    if not pains_text and pains_list:
        pains_text = "; ".join(pains_list)
    if not pains_list and pains_text:
        pains_list = [p.strip() for p in re.split(r"[;\n]", pains_text) if p.strip()][:5]
    features = _as_str_list(draft.get("key_features") or draft.get("keyFeatures"))
    if not features:
        features = list(inferred.get("key_features") or [])
    if not pains_list:
        pains_list = list(inferred.get("pain_points") or [])
        if pains_list and not pains_text:
            pains_text = "; ".join(pains_list)
    social = _as_str_list(draft.get("social_proof") or draft.get("socialProof"))
    adjacent = _as_str_list(draft.get("adjacent_job_titles") or draft.get("adjacentJobTitles"))
    industry = str(draft.get("industry") or (industries[0] if industries else ""))
    icp_desc = str(draft.get("icp_description") or inferred.get("icp_description") or "")
    if not icp_desc and kept_titles:
        icp_desc = ", ".join(kept_titles)

    return {
        "company_name": name,
        "companyName": name,
        "summary": summary,
        "description": str(draft.get("description") or summary),
        "offer": offer or summary,
        "industry": industry,
        "icp_description": icp_desc,
        "client_cure": str(draft.get("client_cure") or ""),
        "pain_points": pains_list,
        "pains": pains_text,
        "key_features": features,
        "keyFeatures": features,
        "social_proof": social,
        "socialProof": social,
        "target_job_titles": kept_titles,
        "job_titles": kept_titles,
        "adjacent_job_titles": adjacent,
        "adjacentJobTitles": adjacent,
        "target_industries": industries,
        "industries": industries,
        "target_company_sizes": sizes,
        "company_sizes": sizes,
        "target_locations": countries,
        "countries": countries,
        "target_company_types": company_types,
        "company_types": company_types,
        "competitors": competitors,
        "search_keywords": keywords[:10],
        "suggested_signal_types": ["search_keyword"] if keywords else [],
        "recommended_signals": cleaned_rec,
        "status": status,
        "need_more_input": need,
        "product_type": product_type,
        "subject_template": str(draft.get("subject_template") or ""),
        "body_template": str(draft.get("body_template") or ""),
    }


def analyze_website_for_agent(
    url: str,
    *,
    crawl_company: bool = False,
    client=None,
    page_html: Optional[str] = None,
    product_blurb: str = "",
) -> dict[str, Any]:
    """Analyze a company website and return Full-Cycle Agent configuration."""
    from engine.llm.website_intake import analyze_website

    intake = analyze_website(
        url,
        client=client,
        crawl_company=crawl_company,
        page_html=page_html,
        product_blurb=product_blurb,
    )
    return intake.as_dict()
