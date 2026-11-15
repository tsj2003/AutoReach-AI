"""Scrape a named source → extract ICP-matching lead candidates.

Firecrawl fetches the page; the LLM extracts structured candidates. This is
lead *discovery*, not verification: scraped pages often lack emails, so a
candidate may arrive without a contactable address — it is created but the
outbound agent will skip it until an email is added/verified (honest, not faked
as "ready to send"). No LinkedIn (ToS). Human approval still gates every send.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ScrapedLead:
    company: str = ""
    company_domain: str = ""
    full_name: str = ""
    title: str = ""
    email: str = ""


def scrape_leads_from_source(
    source_url: str,
    *,
    icp: str,
    firecrawl: Any = None,
    llm: Any = None,
    max_leads: int = 25,
) -> list[ScrapedLead]:
    """Return candidate leads found on `source_url` that match `icp`. Never raises."""
    from engine.integrations.firecrawl_client import FirecrawlClient
    from engine.llm.factory import build_llm_client

    firecrawl = firecrawl or FirecrawlClient()
    llm = llm or build_llm_client()

    if not getattr(firecrawl, "has_api_key", False):
        return []
    markdown = firecrawl.scrape_markdown(source_url)
    if not markdown.strip():
        return []

    prompt = (
        f"From this web page, extract organizations/people that match this ICP:\n{icp}\n\n"
        f"PAGE CONTENT:\n{markdown}\n\n"
        'Return STRICT JSON: {"leads": [{"company": "", "company_domain": "", '
        '"full_name": "", "title": "", "email": ""}]}. '
        f"Up to {max_leads} entries. Only real entries present on the page; leave a field "
        '"" when unknown. Do NOT invent emails.'
    )
    try:
        result = llm.generate_json(prompt=prompt)
        raw = result.data.get("leads", []) if isinstance(getattr(result, "data", None), dict) else []
    except Exception:
        return []

    leads: list[ScrapedLead] = []
    for item in raw[:max_leads]:
        if not isinstance(item, dict):
            continue
        company = str(item.get("company", "")).strip()
        domain = str(item.get("company_domain", "")).strip().lower()
        if not company and not domain:
            continue
        leads.append(ScrapedLead(
            company=company,
            company_domain=domain,
            full_name=str(item.get("full_name", "")).strip(),
            title=str(item.get("title", "")).strip(),
            email=str(item.get("email", "")).strip(),
        ))
    return leads
