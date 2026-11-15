"""Account resolution helpers — domain-keyed, tenant-scoped."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from engine.core.types import Account

_DOMAIN_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$")


def normalize_company_domain(value: str | None) -> str | None:
    raw = (value or "").strip().lower()
    if not raw:
        return None
    if "://" in raw or raw.startswith("www."):
        host = urlparse(raw if "://" in raw else f"https://{raw}").hostname or ""
        raw = host.lower()
    raw = raw.split("/")[0].split("@")[-1].strip(".")
    if raw.startswith("www."):
        raw = raw[4:]
    if not _DOMAIN_RE.match(raw):
        return None
    return raw


def account_id_for(*, tenant_id: str, engagement_id: str, company_domain: str) -> str:
    h = hashlib.sha1(f"{tenant_id}|{engagement_id}|{company_domain}".encode()).hexdigest()[:20]
    return f"acct_{h}"


def upsert_account(
    store,
    *,
    tenant_id: str,
    engagement_id: str,
    company_domain: str,
    company_name: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> Optional[Account]:
    domain = normalize_company_domain(company_domain)
    if not domain:
        return None
    now = datetime.now(timezone.utc)
    aid = account_id_for(tenant_id=tenant_id, engagement_id=engagement_id, company_domain=domain)
    existing = store.get_account(aid)
    merged_evidence = list(getattr(existing, "evidence", None) or [])
    for item in evidence or []:
        if item not in merged_evidence:
            merged_evidence.append(item)
    account = Account(
        id=aid,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        company_domain=domain,
        company_name=company_name or (existing.company_name if existing else None),
        evidence=merged_evidence[:50],
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    store.save_account(account)
    return account
