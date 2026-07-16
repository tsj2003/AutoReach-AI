"""Website → campaign config intake — the "3-minute setup".

Paste a URL; we read the site and draft the whole campaign scaffold (offer, ICP,
client cure, allowed intent signals, and a first email) for the operator to
review and edit. This collapses signup→configured-campaign into one step, the
way the best onboarding flows do.

Trust-preserving by design:
  * Fetches are SSRF-guarded (http/https only, no internal/private hosts).
  * Uses the LLM when available; degrades to a sane editable skeleton otherwise
    (never blocks onboarding on a missing/quota'd API key).
  * The output is a DRAFT for human review — it does not auto-launch anything.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from engine.llm.gemini import GeminiClient, GeminiError, GeminiUnavailable, _ssl_context

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

DEFAULT_SIGNAL_TYPES = ["funding_round", "hiring_surge", "job_change", "tech_adoption"]
_DEFAULT_SUBJECT = "quick question, {first_name}"
_DEFAULT_BODY = (
    "Hi {first_name}, saw what {company} is doing and thought this was worth a note. "
    "We help teams book more qualified meetings without hurting deliverability. "
    "Worth a quick 15-minute chat?"
)


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

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "company_name": self.company_name,
            "summary": self.summary,
            "offer": self.offer,
            "icp_description": self.icp_description,
            "client_cure": self.client_cure,
            "suggested_signal_types": list(self.suggested_signal_types),
            "subject_template": self.subject_template,
            "body_template": self.body_template,
            "source": self.source,
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
        # Resolve and reject any private/loopback/link-local/reserved address.
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
    except Exception:
        return False
    return True


def fetch_website_text(url: str, *, timeout: int = 12, max_chars: int = 8000) -> str:
    """Fetch a page and return visible text. Returns '' on any failure (never raises)."""
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not is_safe_fetch_url(url):
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AttainlyOnboardingBot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            raw = resp.read(2_000_000).decode("utf-8", errors="ignore")
    except Exception:
        return ""
    raw = _SCRIPT_STYLE_RE.sub(" ", raw)
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", raw)).strip()
    return text[:max_chars]


_PROMPT = """You are onboarding a new user to a B2B outbound-sales tool by reading THEIR website.
Infer their business so we can configure outbound campaigns FOR them.

Website text:
{text}

Return STRICT JSON:
{{
  "company_name": "their company name",
  "summary": "one sentence: what they do",
  "offer": "one first-person sentence pitching what they sell, e.g. 'We help X do Y'",
  "icp_description": "their ideal customer (role + company type)",
  "client_cure": "the core outcome/pain their offer solves, one sentence",
  "suggested_signal_types": ["up to 4 of: funding_round, hiring_surge, job_change, tech_adoption, leadership_change, product_launch"],
  "subject_template": "a short, specific cold-email subject including {{first_name}}",
  "body_template": "a 3-sentence cold email using {{first_name}} and {{company}} — specific, no hype, no cliches"
}}"""


def analyze_website(url: str, *, client: GeminiClient | None = None) -> WebsiteIntake:
    """Return a drafted campaign scaffold from a website. Never raises."""
    text = fetch_website_text(url)
    client = client or GeminiClient()

    if text and getattr(client, "has_api_key", False):
        try:
            result = client.generate_json(prompt=_PROMPT.format(text=text))
            d = result.data if isinstance(result.data, dict) else {}
            signals = [str(s) for s in (d.get("suggested_signal_types") or []) if str(s)][:4]
            return WebsiteIntake(
                url=url,
                company_name=str(d.get("company_name") or _domain_name(url)),
                summary=str(d.get("summary") or ""),
                offer=str(d.get("offer") or ""),
                icp_description=str(d.get("icp_description") or ""),
                client_cure=str(d.get("client_cure") or ""),
                suggested_signal_types=signals or list(DEFAULT_SIGNAL_TYPES),
                subject_template=str(d.get("subject_template") or _DEFAULT_SUBJECT),
                body_template=str(d.get("body_template") or _DEFAULT_BODY),
                source="llm",
            )
        except (GeminiError, GeminiUnavailable):
            pass
        except Exception:
            pass

    return _fallback(url)


def _fallback(url: str) -> WebsiteIntake:
    """Editable skeleton when the site can't be read or no LLM is configured."""
    name = _domain_name(url)
    return WebsiteIntake(
        url=url,
        company_name=name,
        summary="",
        offer=f"We help teams achieve <outcome> — edit this to describe what {name} sells.",
        icp_description="e.g. Heads of Sales at 20-200 person B2B software companies.",
        client_cure="e.g. book more qualified meetings without burning sender reputation.",
        suggested_signal_types=list(DEFAULT_SIGNAL_TYPES),
        subject_template=_DEFAULT_SUBJECT,
        body_template=_DEFAULT_BODY,
        source="fallback",
    )
