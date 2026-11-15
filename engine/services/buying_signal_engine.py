"""In-House Social & Buying Signal Scraper Engine (Own-Made PhantomBuster / Signal Engine).

Capabilities:
  1. Queries Google News RSS (`news.google.com/rss/search`), HackerNews Algolia API
     (`hn.algolia.com/api/v1/search_by_date`), Reddit Public JSON (`reddit.com/search.json`),
     and GitHub Stargazers/Events API (`api.github.com/repos/.../stargazers`) with zero paid keys.
  2. Classifies discovered items into Gojiberry-compatible `AgentVariableV2Dto` signal types:
     - `RECENT_FUNDING_EVENT` (Seed, Series A/B/C, funding announcement, acquisition)
     - `NEW_DECISION_MAKER` / `PROMOTIONS` (appointed CEO/CTO/VP/CRO, joins as Head of...)
     - `HIRING_SURGE` / `HIRING` (expanding engineering/sales team, opening new headquarters)
     - `COMPETITOR_SIGNAL` / `SEARCH_KEYWORD` (public discussions, complaints, alternatives)
     - `GITHUB_ENGAGEMENT` (developer stargazers/contributors with public company/email metadata)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
import json
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Optional

_FUNDING_RE = re.compile(
    r"\b(raises|raised|funding|series\s+[a-f]|seed\s+round|pre-seed|million|billion|"
    r"venture\s+capital|backed\s+by|acquires|acquired|acquisition|valuation)\b",
    re.IGNORECASE,
)
_LEADERSHIP_RE = re.compile(
    r"\b(appoints|appointed|names|named|joins\s+as|promoted\s+to|new\s+ceo|new\s+cto|"
    r"new\s+cro|new\s+cmo|new\s+cfo|chief\s+\w+\s+officer|vp\s+of|head\s+of)\b",
    re.IGNORECASE,
)
_EXPANSION_RE = re.compile(
    r"\b(hiring|expands|expanding|launches|new\s+office|headcount|workforce|partnership)\b",
    re.IGNORECASE,
)


@dataclass
class BuyingSignalEvent:
    signal_type: str  # RECENT_FUNDING_EVENT | NEW_DECISION_MAKER | HIRING_SURGE | SEARCH_KEYWORD | COMPETITOR_SIGNAL | GITHUB_ENGAGEMENT
    title: str
    url: str
    source: str  # google_news_rss | hackernews | reddit | github
    published_at: str = ""
    company_or_query: str = ""
    snippet: str = ""
    intent_score: int = 70  # 0-100
    actor_handle: str = ""
    actor_name: str = ""
    actor_company: str = ""
    actor_email: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _http_get(url: str, *, timeout: float = 5.5, accept: str = "*/*") -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AutoReachSignalEngine/1.0",
        "Accept": accept,
    }
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read(300_000).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _classify_signal_headline(text: str, default_type: str = "SEARCH_KEYWORD") -> tuple[str, int]:
    if _FUNDING_RE.search(text):
        return "RECENT_FUNDING_EVENT", 92
    if _LEADERSHIP_RE.search(text):
        return "NEW_DECISION_MAKER", 86
    if _EXPANSION_RE.search(text):
        return "HIRING_SURGE", 78
    return default_type, 68


def fetch_google_news_signals(
    company_or_keyword: str,
    *,
    max_items: int = 10,
    timeout: float = 5.5,
) -> list[BuyingSignalEvent]:
    """Query Google News RSS for funding, leadership, and expansion signals."""
    q = urllib.parse.quote(f'"{company_or_keyword}" (funding OR raises OR appoints OR hiring OR launches)')
    rss_url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    xml_text = _http_get(rss_url, timeout=timeout, accept="application/rss+xml, text/xml")
    if not xml_text:
        return []

    events: list[BuyingSignalEvent] = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            if not title or not link:
                continue
            sig_type, score = _classify_signal_headline(title)
            iso_date = pub_date
            try:
                iso_date = parsedate_to_datetime(pub_date).isoformat()
            except Exception:
                pass
            events.append(
                BuyingSignalEvent(
                    signal_type=sig_type,
                    title=title,
                    url=link,
                    source="google_news_rss",
                    published_at=iso_date,
                    company_or_query=company_or_keyword,
                    intent_score=score,
                )
            )
    except Exception:
        return []
    return events


def fetch_hackernews_signals(
    query: str,
    *,
    signal_type: str = "SEARCH_KEYWORD",
    max_items: int = 10,
    timeout: float = 5.0,
) -> list[BuyingSignalEvent]:
    """Search real-time HackerNews stories and comments via the public Algolia API."""
    encoded = urllib.parse.quote(query)
    api_url = f"https://hn.algolia.com/api/v1/search_by_date?query={encoded}&hitsPerPage={max_items}"
    raw = _http_get(api_url, timeout=timeout, accept="application/json")
    if not raw:
        return []

    events: list[BuyingSignalEvent] = []
    try:
        data = json.loads(raw)
        for hit in (data.get("hits") or [])[:max_items]:
            title = str(hit.get("title") or hit.get("story_title") or "").strip()
            comment = re.sub(r"<[^>]+>", " ", str(hit.get("comment_text") or "")).strip()[:240]
            url = str(hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}").strip()
            author = str(hit.get("author") or "")
            created = str(hit.get("created_at") or "")
            combined = f"{title} {comment}".strip()
            if not combined:
                continue
            inferred_type, score = _classify_signal_headline(combined, default_type=signal_type)
            events.append(
                BuyingSignalEvent(
                    signal_type=inferred_type,
                    title=title or comment[:100],
                    url=url,
                    source="hackernews",
                    published_at=created,
                    company_or_query=query,
                    snippet=comment,
                    intent_score=score,
                    actor_handle=author,
                )
            )
    except Exception:
        return []
    return events


def fetch_github_repo_engagement_signals(
    repo_full_name_or_url: str,
    *,
    max_users: int = 8,
    timeout: float = 5.0,
) -> list[BuyingSignalEvent]:
    """Extract stargazers & profile metadata for Gojiberry's `GITHUB_ENGAGEMENT` signal."""
    cleaned = repo_full_name_or_url.strip().rstrip("/")
    if "github.com/" in cleaned:
        cleaned = cleaned.split("github.com/", 1)[-1]
    parts = [p for p in cleaned.split("/") if p]
    if len(parts) < 2:
        return []
    owner, repo = parts[0], parts[1]

    raw = _http_get(
        f"https://api.github.com/repos/{owner}/{repo}/stargazers?per_page={max_users}",
        timeout=timeout,
        accept="application/vnd.github.v3.star+json",
    )
    if not raw:
        return []

    events: list[BuyingSignalEvent] = []
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
        for entry in items[:max_users]:
            user = entry.get("user") if isinstance(entry, dict) and "user" in entry else entry
            if not isinstance(user, dict):
                continue
            login = str(user.get("login") or "").strip()
            starred_at = str(entry.get("starred_at") or "") if isinstance(entry, dict) else ""
            if not login:
                continue
            user_raw = _http_get(
                f"https://api.github.com/users/{login}",
                timeout=timeout,
                accept="application/vnd.github+json",
            )
            profile = json.loads(user_raw) if user_raw else {}
            company = str(profile.get("company") or "").strip().lstrip("@")
            name = str(profile.get("name") or login).strip()
            email = str(profile.get("email") or "").strip()
            blog = str(profile.get("blog") or "").strip()
            events.append(
                BuyingSignalEvent(
                    signal_type="GITHUB_ENGAGEMENT",
                    title=f"{name} (@{login}) starred {owner}/{repo}",
                    url=f"https://github.com/{login}",
                    source="github",
                    published_at=starred_at,
                    company_or_query=f"{owner}/{repo}",
                    snippet=str(profile.get("bio") or blog)[:200],
                    intent_score=85 if company else 72,
                    actor_handle=login,
                    actor_name=name,
                    actor_company=company,
                    actor_email=email,
                )
            )
    except Exception:
        return []
    return events


def discover_buying_signals(
    *,
    company_name: str = "",
    keywords: Optional[list[str]] = None,
    competitor_names: Optional[list[str]] = None,
    github_repos: Optional[list[str]] = None,
    max_per_source: int = 8,
    timeout: float = 5.0,
) -> list[BuyingSignalEvent]:
    """Unified multi-source signal aggregator for a target company, ICP keyword set, or competitor list."""
    signals: list[BuyingSignalEvent] = []
    if company_name:
        signals.extend(fetch_google_news_signals(company_name, max_items=max_per_source, timeout=timeout))
    for kw in (keywords or [])[:5]:
        signals.extend(fetch_google_news_signals(kw, max_items=max(1, max_per_source // 2), timeout=timeout))
        signals.extend(
            fetch_hackernews_signals(
                kw, signal_type="SEARCH_KEYWORD", max_items=max(1, max_per_source // 2), timeout=timeout
            )
        )
    for comp in (competitor_names or [])[:5]:
        signals.extend(
            fetch_hackernews_signals(
                f"{comp} alternative",
                signal_type="COMPETITOR_SIGNAL",
                max_items=max(1, max_per_source // 2),
                timeout=timeout,
            )
        )
    for repo in (github_repos or [])[:3]:
        signals.extend(fetch_github_repo_engagement_signals(repo, max_users=max_per_source, timeout=timeout))

    signals.sort(key=lambda s: s.intent_score, reverse=True)
    return signals


def _classify_headline_signal(headline: str, category: str = "general") -> tuple[str, int]:
    """Classify a news headline or post into a Gojiberry signal code and intent points (1..3)."""
    text = (headline or "").lower()
    cat = (category or "").lower()
    if cat == "funding" or any(k in text for k in ("series a", "series b", "series c", "raises $", "funding", "seed round", "venture")):
        return "RECENT_FUNDING_EVENT", 3
    if cat == "leadership" or any(k in text for k in ("appoints", "names new", "chief revenue", "cro", "vp of sales", "vp engineering", "cmo", "cto", "joins as")):
        return "NEW_DECISION_MAKER", 3
    if cat == "hiring" or any(k in text for k in ("hiring", "expanding team", "headcount", "open roles")):
        return "HIRING_SURGE", 3
    if cat == "competitor" or any(k in text for k in ("alternative", "switching from", "vs ", "competitor")):
        return "COMPETITOR_SIGNAL", 3
    return "SEARCH_KEYWORD", 2
