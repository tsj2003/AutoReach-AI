"""Firecrawl client — web scraping for website-read + lead sourcing.

Two uses:
  * scrape_markdown(url): clean main-content markdown of a page (client website
    read for onboarding, or a prospect page for research/grounding).
Feeds the LLM layer; never a lead *database* — it returns page content, from
which the LLM extracts candidates. Graceful: returns "" on any failure so the
caller falls back (never crashes the flow). Uses FIRECRAWL_API_KEY from env.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from engine.llm.gemini import _ssl_context

_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"


class FirecrawlClient:
    def __init__(self, *, api_key: Optional[str] = None, timeout_seconds: int = 45) -> None:
        self._key = (api_key if api_key is not None else os.getenv("FIRECRAWL_API_KEY", "")).strip()
        self._timeout = timeout_seconds

    @property
    def has_api_key(self) -> bool:
        return bool(self._key)

    def scrape_markdown(self, url: str, *, max_chars: int = 12000) -> str:
        """Return main-content markdown for a URL, or '' on any failure."""
        if not self._key or not url:
            return ""
        payload = {"url": url, "formats": ["markdown"], "onlyMainContent": True}
        try:
            req = urllib.request.Request(
                _SCRAPE_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout, context=_ssl_context()) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, Exception):
            return ""
        md = ""
        if isinstance(data, dict):
            md = (data.get("data") or {}).get("markdown") or data.get("markdown") or ""
        return str(md)[:max_chars]
