"""
M8 — ESP matching via MX-record lookup.

Detects a prospect's email provider so the runtime can route through a
matching mailbox (Gmail→Gmail lands in the primary tab far more often than
Gmail→Outlook). MX lookups are cached 24h in-memory.
"""

from __future__ import annotations

import time
from typing import Optional

PROVIDER_PATTERNS = {
    "google": ["google.com", "googlemail.com", "aspmx.l.google.com", "gmail.com"],
    "microsoft": ["outlook.com", "protection.outlook.com", "microsoft.com", "hotmail.com"],
    "zoho": ["zoho.com", "zoho.in", "zohomail.com"],
}

_CACHE_TTL_SECONDS = 86_400


class EspMatcher:
    def __init__(self) -> None:
        # domain -> (provider, expires_at_epoch)
        self._cache: dict[str, tuple[str, float]] = {}

    def detect_provider(self, email: str) -> str:
        """Returns 'google' | 'microsoft' | 'zoho' | 'other'."""
        if not email or "@" not in email:
            return "other"
        domain = email.split("@", 1)[1].lower().strip()

        cached = self._cache.get(domain)
        if cached and cached[1] > time.time():
            return cached[0]

        provider = self._lookup(domain)
        self._cache[domain] = (provider, time.time() + _CACHE_TTL_SECONDS)
        return provider

    def _lookup(self, domain: str) -> str:
        try:
            import dns.resolver  # type: ignore

            answers = dns.resolver.resolve(domain, "MX", lifetime=3.0)
            exchanges = " ".join(str(r.exchange).lower() for r in answers)
        except Exception:
            # No DNS / no MX / timeout — fall back to domain-name heuristic.
            exchanges = domain

        for provider, patterns in PROVIDER_PATTERNS.items():
            if any(p in exchanges for p in patterns):
                return provider
        return "other"

    def select_mailbox(self, prospect_email: str, mailboxes: list) -> Optional[object]:
        """
        Pick the best mailbox for a prospect. `mailboxes` is a list of objects
        with a `.provider` attribute. Prefers same-provider, falls back to first.
        """
        if not mailboxes:
            return None
        target = self.detect_provider(prospect_email)
        for mb in mailboxes:
            if getattr(mb, "provider", None) == target:
                return mb
        return mailboxes[0]
