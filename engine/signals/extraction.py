"""Conservative signal extraction from unstructured text (RSS entries, etc.).

Does NOT manufacture signals. Rejects candidates without sufficient evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from engine.signals.registry import get_signal_registry

_WS_RE = re.compile(r"\s+")

# Keyword → canonical signal type (registry keys only)
_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("funding_round", ("funding", "raised", "series a", "series b", "series c", "seed round", "investment")),
    ("hiring_surge", ("hiring", "hires", "headcount", "workforce expansion")),
    ("job_posting", ("job opening", "job posting", "open role", "we're hiring", "now hiring")),
    ("leadership_change", ("ceo", "cto", "cfo", "appoints", "named as", "joins as", "executive")),
    ("product_launch", ("launches", "launch", "introduces", "unveils", "new product")),
    ("acquisition", ("acquires", "acquisition", "acquired", "merger")),
    ("technology_adoption", ("adopts", "migrates to", "partners with", "integrates with")),
    ("geographic_expansion", ("expansion", "new office", "opens office", "enters market")),
)


@dataclass(frozen=True)
class ExtractionCandidate:
    signal_type: str
    company_domain: str
    company_name: str | None
    confidence: float
    summary: str
    source_url: str | None
    matched_reason: str
    raw_excerpt: str


def _clean_text(text: str, *, max_len: int = 2000) -> str:
    cleaned = _WS_RE.sub(" ", (text or "").strip())
    return cleaned[:max_len]


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if not host or host in {"feedburner.com", "feeds.feedburner.com", "news.google.com"}:
            return None
        if "." not in host:
            return None
        return host
    except Exception:
        return None


def _company_from_title(title: str) -> tuple[str | None, str | None]:
    """Extract company name and infer domain conservatively from title patterns."""

    # "Acme Corp raises $10M" → Acme Corp
    m = re.match(r"^([A-Z][A-Za-z0-9&.\- ]{1,60}?)\s+(raises|raised|acquires|launches|hires|appoints)\b", title)
    if m:
        name = m.group(1).strip()
        slug = re.sub(r"[^a-z0-9]", "", name.lower())
        if len(slug) >= 3:
            return name, f"{slug}.com"  # inferred — lower confidence applied by caller
    return None, None


def extract_signal_candidate(
    *,
    title: str,
    description: str = "",
    link: str | None = None,
    allowed_signal_types: set[str] | None = None,
) -> ExtractionCandidate | None:
    """Return a signal candidate or None if evidence is insufficient."""

    registry = get_signal_registry()
    text = _clean_text(f"{title}. {description}".lower())
    if len(text) < 20:
        return None

    matched_type: str | None = None
    matched_keyword: str | None = None
    for signal_type, keywords in _KEYWORD_RULES:
        if allowed_signal_types and signal_type not in allowed_signal_types:
            continue
        if not registry.is_known(signal_type):
            continue
        for kw in keywords:
            if kw in text:
                matched_type = signal_type
                matched_keyword = kw
                break
        if matched_type:
            break

    if not matched_type or not matched_keyword:
        return None

    domain = _domain_from_url(link)
    company_name: str | None = None
    confidence = 0.55  # base: keyword match only

    if not domain:
        company_name, inferred = _company_from_title(title.strip())
        if inferred:
            domain = inferred
            confidence = 0.45  # inferred domain — below actionable threshold alone
        else:
            return None  # no entity anchor

    if _domain_from_url(link) == domain:
        confidence = 0.72  # real link domain
        company_name = company_name or domain.split(".")[0].title()

    if confidence < 0.5:
        return None

    summary = _clean_text(title, max_len=300)
    return ExtractionCandidate(
        signal_type=matched_type,
        company_domain=domain.lower(),
        company_name=company_name,
        confidence=confidence,
        summary=summary,
        source_url=link,
        matched_reason=f"keyword '{matched_keyword}' in feed entry",
        raw_excerpt=_clean_text(description or title, max_len=500),
    )
