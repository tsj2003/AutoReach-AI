"""Website → campaign config intake — the "3-minute setup" + Gojiberry Full-Cycle Agent Wizard.

Paste a URL; we read the site and draft the whole campaign scaffold (offer, ICP,
client cure, allowed intent signals, multichannel Email + LinkedIn sequence,
18 Gojiberry AI prompt templates, and live company intelligence) for the operator
to review and edit.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

from engine.llm.factory import build_llm_client
from engine.llm.gemini import GeminiClient, GeminiError, GeminiUnavailable, _ssl_context
from engine.llm.prompt_templates import list_prompt_templates

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

DEFAULT_SIGNAL_TYPES: list[str] = []
_DEFAULT_SUBJECT = "quick question, {first_name}"
_DEFAULT_BODY = (
    "Hi {first_name}, saw what {company} is doing and thought this was worth a note. "
    "We help teams book more qualified meetings without hurting deliverability. "
    "Worth a quick 15-minute chat?"
)

_DEFAULT_MULTICHANNEL_SEQUENCE = [
    {
        "step": 1,
        "type": "visitProfile",
        "channel": "linkedin",
        "delay_days": 0,
        "label": "Day 0 · Visit LinkedIn Profile",
        "message_mode": "ai",
        "template_key": "",
    },
    {
        "step": 2,
        "type": "likePosts",
        "channel": "linkedin",
        "delay_days": 1,
        "label": "Day 1 · Like Recent LinkedIn Post",
        "message_mode": "ai",
        "template_key": "",
    },
    {
        "step": 3,
        "type": "invitationNote",
        "channel": "linkedin",
        "delay_days": 1,
        "label": "Day 1 · Send Connection Request with Signal Note",
        "message_mode": "ai",
        "template_key": "connection_note",
    },
    {
        "step": 4,
        "type": "message",
        "channel": "linkedin",
        "delay_days": 3,
        "label": "Day 3 · Signal-First LinkedIn DM",
        "message_mode": "ai",
        "template_key": "signal_first_icebreaker",
    },
    {
        "step": 5,
        "type": "email",
        "channel": "email",
        "delay_days": 4,
        "label": "Day 4 · Personalized Cold Email Fallback",
        "message_mode": "ai",
        "template_key": "problem_value_hook",
        "subject_template": _DEFAULT_SUBJECT,
        "body_template": _DEFAULT_BODY,
    },
]


@dataclass
class WebsiteIntake:
    url: str
    company_name: str
    summary: str
    offer: str
    icp_description: str
    client_cure: str
    suggested_signal_types: list
    subject_template: str
    body_template: str
    source: str  # "llm" | "fallback"
    # Extended Gojiberry Full-Cycle Agent fields (with defaults for backward compatibility)
    company_summary: str = ""
    value_proposition: str = ""
    pain_points: list[str] = field(default_factory=list)
    target_job_titles: list[str] = field(default_factory=list)
    target_industries: list[str] = field(default_factory=list)
    target_company_sizes: list[str] = field(default_factory=list)
    target_locations: list[str] = field(default_factory=list)
    target_company_types: list[str] = field(default_factory=list)
    detected_technologies: list[dict[str, Any]] = field(default_factory=list)
    hiring_signal: dict[str, Any] = field(default_factory=dict)
    decision_makers: list[dict[str, Any]] = field(default_factory=list)
    recommended_signals: list[dict[str, Any]] = field(default_factory=list)
    multichannel_sequence: list[dict[str, Any]] = field(default_factory=list)
    prompt_templates: list[dict[str, Any]] = field(default_factory=list)
    status: str = "ok"  # "ok" | "low_evidence"
    need_more_input: str = ""
    product_type: str = ""
    # Gojiberry generate-icp-from-website / generate-website-analysis-v2 aliases
    search_keywords: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    key_features: list[str] = field(default_factory=list)
    social_proof: list[str] = field(default_factory=list)
    adjacent_job_titles: list[str] = field(default_factory=list)
    industry: str = ""
    pains: str = ""
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        # Empty titles/signals mean "we do not know" — never refill Head of Sales / funding.
        from engine.services.website_analyzer import GOJIBERRY_EVENT_SIGNAL_DEFAULTS

        comp_summary = self.company_summary or self.summary or self.description
        val_prop = self.value_proposition or self.offer or self.description
        pains = list(self.pain_points)
        titles = list(self.target_job_titles)
        industries = list(self.target_industries)
        sizes = list(self.target_company_sizes)
        locations = list(self.target_locations)
        comp_types = list(self.target_company_types)
        rec_signals = list(self.recommended_signals)
        keywords = list(self.search_keywords)
        seq = list(self.multichannel_sequence) if self.multichannel_sequence else list(_DEFAULT_MULTICHANNEL_SEQUENCE)
        templates = list(self.prompt_templates) if self.prompt_templates else list_prompt_templates()
        status = self.status or ("low_evidence" if not titles else "ok")
        pains_text = self.pains or "; ".join(pains)
        return {
            "url": self.url,
            "company_name": self.company_name,
            "companyName": self.company_name,
            "summary": self.summary,
            "description": self.description or comp_summary,
            "company_summary": comp_summary,
            "offer": self.offer,
            "value_proposition": val_prop,
            "industry": self.industry or (industries[0] if industries else ""),
            "icp_description": self.icp_description,
            "client_cure": self.client_cure,
            "pain_points": pains,
            "pains": pains_text,
            "key_features": list(self.key_features),
            "keyFeatures": list(self.key_features),
            "social_proof": list(self.social_proof),
            "socialProof": list(self.social_proof),
            "target_job_titles": titles,
            "job_titles": titles,
            "adjacent_job_titles": list(self.adjacent_job_titles),
            "adjacentJobTitles": list(self.adjacent_job_titles),
            "target_industries": industries,
            "industries": industries,
            "target_company_sizes": sizes,
            "company_sizes": sizes,
            "target_locations": locations,
            "countries": locations,
            "target_company_types": comp_types,
            "company_types": comp_types,
            "competitors": list(self.competitors),
            "ignoredCompanies": list(self.competitors),
            "ignored_companies": list(self.competitors),
            "search_keywords": keywords[:10],
            "suggested_signal_types": list(self.suggested_signal_types),
            "recommended_signals": rec_signals,
            "event_signal_defaults": [dict(s) for s in GOJIBERRY_EVENT_SIGNAL_DEFAULTS],
            "detected_technologies": list(self.detected_technologies),
            "hiring_signal": dict(self.hiring_signal),
            "decision_makers": list(self.decision_makers),
            "multichannel_sequence": seq,
            "prompt_templates": templates,
            "subject_template": self.subject_template,
            "body_template": self.body_template,
            "source": self.source,
            "status": status,
            "need_more_input": self.need_more_input,
            "product_type": self.product_type,
        }


def _domain_name(url: str) -> str:
    host = urllib.parse.urlparse(url if "//" in url else f"//{url}").hostname or url
    host = host.lstrip("www.")
    return host.split(".")[0].capitalize() if host else "Your company"


def is_safe_fetch_url(url: str) -> bool:
    """SSRF guard: only public http(s) hosts; never internal/private addresses."""
    try:
        parsed = urllib.parse.urlparse(url if "//" in url else f"https://{url}")
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host or host.lower() in ("localhost", "metadata.google.internal"):
        return False
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
    except Exception:
        return False
    return True


def fetch_website_text(url: str, *, timeout: int = 12, max_chars: int = 8000) -> str:
    """Fetch a page and return visible text. Returns '' on any failure (never raises)."""
    from engine.services.website_analyzer import collect_website_evidence

    if not url:
        return ""
    evidence = collect_website_evidence(url)
    return (evidence.combined_text or "")[:max_chars]


_PROMPT = """Extract a Gojiberry-style website-to-agent blueprint from crawled evidence.
This is generate-website-analysis-v2 + generate-icp-from-website + generate-engagement-keywords-v2 in one JSON object.
The client only POSTs {{ websiteUrl }} — you must work from crawled evidence, never from a fixed SaaS ICP.

CLASSIFY the site first as product_type:
- "app_login": password / sign-in wall, Cloudflare/anti-bot shell, almost no marketing copy
- "consumer_marketplace": shopping/marketplace for consumers (cart, millions of products, we help you shop)
- "b2b_product": software/service sold to a business or operator audience
- "marketing_site": other public marketing page

job_titles RULES (role TYPES, never a fixed exec pack):
- app_login or consumer_marketplace: ALWAYS []. Do not invent VP Revenue, Head of Sales, Shop Owner, or "consumers".
- b2b_product / marketing_site: infer buyer ROLE TYPES from product-category language when exact titles are absent.
  "for independent shops" / "built for shop owners" → ["Shop Owner"] (or "Independent Shop Owner")
  "for sales teams" → ["Sales Manager"]
  "for hospital HR teams" → ["Hospital HR Manager"]
  "for developers" → ["Developer"]
- If the only audience is you / consumers / customers / shoppers / people / businesses / teams with no department: job_titles = [].
- NEVER emit Head of Sales, VP Revenue, VP of Sales, CRO, Head of Growth, GTM Engineer unless those exact words appear in evidence.

OTHER RULES:
- Use ONLY the evidence (title, h1, meta, og, JSON-LD, extra paths, visible copy, optional operator blurb).
- NEVER invent a consumer marketplace pitch such as "we help consumers shop" unless that sentence is on the page.
- app_login / thin anti-bot: status "low_evidence", empty job_titles, empty search_keywords, empty competitors.
- consumer_marketplace: status "ok" if there is a real description; keep job_titles empty; search_keywords from on-page product language.
- search_keywords: 1 to 3 word phrases a LinkedIn buyer of THIS product would engage with, taken from the page. Max 10. Not a generic outbound/funding pack.
- competitors: company names the page names as alternatives. Empty if unknown. These become ignoredCompanies, NOT COMPETITOR_PAGE_URL unless a LinkedIn company URL is present.
- Do not emit LOOKALIKE or WEBSITE_VISITOR as recommended_signals (those are agentType, not website variables).
- Do not emit RECENT_FUNDING_EVENT or HIRING unless the page discusses fundraising / hiring. UI defaults for those live separately.

Evidence:
{text}

Return STRICT JSON:
{{
  "status": "ok" or "low_evidence",
  "product_type": "b2b_product" or "consumer_marketplace" or "app_login" or "marketing_site",
  "need_more_input": "",
  "company_name": "",
  "companyName": "",
  "summary": "one sentence grounded in evidence",
  "description": "company description from the page",
  "offer": "what they sell, from the page",
  "industry": "",
  "icp_description": "buyer role types + company type if evidenced, else empty",
  "client_cure": "",
  "pain_points": [],
  "pains": "",
  "key_features": [],
  "keyFeatures": [],
  "social_proof": [],
  "job_titles": [],
  "adjacent_job_titles": [],
  "industries": [],
  "company_sizes": [],
  "countries": [],
  "company_types": [],
  "competitors": [],
  "search_keywords": [],
  "subject_template": "short subject including {{first_name}}",
  "body_template": "3-sentence email using {{first_name}} and {{company}}"
}}"""


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def _intake_from_inferred(url: str, inferred: dict[str, Any], *, source: str) -> WebsiteIntake:
    name = str(inferred.get("company_name") or inferred.get("companyName") or _domain_name(url))
    summary = str(inferred.get("summary") or inferred.get("description") or "")
    offer = str(inferred.get("offer") or summary)
    titles = _as_list(inferred.get("job_titles") or inferred.get("target_job_titles"))
    industries = _as_list(inferred.get("industries") or inferred.get("target_industries"))
    sizes = _as_list(inferred.get("company_sizes") or inferred.get("target_company_sizes"))
    locations = _as_list(inferred.get("countries") or inferred.get("target_locations"))
    types = _as_list(inferred.get("company_types") or inferred.get("target_company_types"))
    keywords = _as_list(inferred.get("search_keywords"))[:10]
    pains = _as_list(inferred.get("pain_points"))
    pains_text = str(inferred.get("pains") or "")
    if not pains and pains_text:
        pains = [x.strip() for x in pains_text.split(";") if x.strip()]
    rec = [dict(s) for s in (inferred.get("recommended_signals") or []) if isinstance(s, dict)]
    return WebsiteIntake(
        url=url,
        company_name=name,
        summary=summary,
        offer=offer,
        icp_description=str(inferred.get("icp_description") or ""),
        client_cure=str(inferred.get("client_cure") or ""),
        suggested_signal_types=[str(s) for s in (inferred.get("suggested_signal_types") or []) if str(s)][:4],
        subject_template=str(inferred.get("subject_template") or _DEFAULT_SUBJECT),
        body_template=str(inferred.get("body_template") or _DEFAULT_BODY),
        source=source,
        company_summary=summary,
        value_proposition=offer,
        pain_points=pains,
        target_job_titles=titles,
        target_industries=industries,
        target_company_sizes=sizes,
        target_locations=locations,
        target_company_types=types,
        recommended_signals=rec,
        status=str(inferred.get("status") or "ok"),
        need_more_input=str(inferred.get("need_more_input") or ""),
        product_type=str(inferred.get("product_type") or ""),
        search_keywords=keywords,
        competitors=_as_list(inferred.get("competitors")),
        key_features=_as_list(inferred.get("key_features") or inferred.get("keyFeatures")),
        social_proof=_as_list(inferred.get("social_proof") or inferred.get("socialProof")),
        adjacent_job_titles=_as_list(inferred.get("adjacent_job_titles") or inferred.get("adjacentJobTitles")),
        industry=str(inferred.get("industry") or (industries[0] if industries else "")),
        pains=pains_text,
        description=str(inferred.get("description") or summary),
    )


def analyze_website(
    url: str,
    *,
    client: GeminiClient | None = None,
    crawl_company: bool = False,
    page_html: str | None = None,
    product_blurb: str = "",
    extra_bodies: dict[str, str] | None = None,
) -> WebsiteIntake:
    """Return a drafted campaign scaffold from a website. Never raises."""
    from engine.services.website_analyzer import (
        collect_website_evidence,
        infer_icp_from_evidence,
        sanitize_llm_icp,
    )

    evidence = collect_website_evidence(
        url,
        homepage_html=page_html,
        product_blurb=product_blurb,
        extra_bodies=extra_bodies,
        fetch_extras=page_html is None,
    )
    inferred = infer_icp_from_evidence(evidence)
    client = client or build_llm_client()

    detected_techs: list[dict[str, Any]] = []
    hiring_sig: dict[str, Any] = {}
    decision_makers: list[dict[str, Any]] = []

    if crawl_company and is_safe_fetch_url(url):
        try:
            from engine.services.company_intel_engine import crawl_and_fingerprint_company
            intel = crawl_and_fingerprint_company(url, timeout=4.0)
            detected_techs = list(intel.technologies)
            hiring_sig = asdict(intel.hiring)
            decision_makers = [asdict(dm) for dm in intel.decision_makers]
        except Exception:
            pass

    text = evidence.evidence_blob()
    # Gojiberry's client POSTs only { websiteUrl }; the server scrapes. We crawl here
    # and call the LLM on marketing copy. Login walls without a blurb skip the LLM so
    # we do not invent a SaaS ICP (client shows the Cloudflare/login empty form).
    login_wall = evidence.is_login_gated and evidence.richness in {"thin", "empty"}
    use_llm = bool(
        getattr(client, "has_api_key", False)
        and (
            evidence.product_blurb.strip()
            or evidence.richness == "rich"
            or (evidence.combined_text and not login_wall)
        )
    )
    if use_llm:
        try:
            result = client.generate_json(prompt=_PROMPT.format(text=text))
            d = result.data if isinstance(result.data, dict) else {}
            cleaned = sanitize_llm_icp(d, evidence)
            intake = _intake_from_inferred(url, cleaned, source="llm")
            intake.detected_technologies = detected_techs
            intake.hiring_signal = hiring_sig
            intake.decision_makers = decision_makers
            return intake
        except (GeminiError, GeminiUnavailable):
            pass
        except Exception:
            pass

    intake = _intake_from_inferred(url, inferred, source="evidence" if evidence.combined_text or evidence.primary.title else "fallback")
    if intake.source == "fallback" and not (evidence.combined_text or evidence.primary.title):
        intake = _fallback(url)
        intake.status = "low_evidence"
        intake.need_more_input = str(inferred.get("need_more_input") or intake.need_more_input)
    intake.detected_technologies = detected_techs
    intake.hiring_signal = hiring_sig
    intake.decision_makers = decision_makers
    return intake


def _fallback(url: str) -> WebsiteIntake:
    """Honest empty scaffold when the site can't be read — never a fake SaaS ICP."""
    name = _domain_name(url)
    return WebsiteIntake(
        url=url,
        company_name=name,
        summary="",
        offer="",
        icp_description="",
        client_cure="",
        suggested_signal_types=[],
        subject_template=_DEFAULT_SUBJECT,
        body_template=_DEFAULT_BODY,
        source="fallback",
        company_summary="",
        value_proposition="",
        status="low_evidence",
        need_more_input=(
            "We could not generate a reliable ICP from this URL. This usually happens when the "
            "page is a login wall or is protected by an anti-bot filter like Cloudflare. "
            "Try a public marketing / about URL, or paste a one-sentence product blurb."
        ),
    )
