"""Shared merge + leftover-token checks for outbound email copy."""

from __future__ import annotations

import re
from typing import Optional

UNRENDERED_TOKEN_RE = re.compile(r"\{[a-z_][a-z0-9_]*\}")

GENERIC_BOILERPLATE = (
    "businesses of all sizes",
    "flexible payment and billing solutions",
    "accept payments globally",
    "manage subscriptions with ease",
    "support your growth",
    "streamline payments with",
)


def first_name_from_payload(payload: dict) -> str:
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
    explicit = str(payload.get("first_name") or raw.get("first_name") or "").strip()
    if explicit:
        return explicit.split()[0]
    full = str(payload.get("full_name") or payload.get("to_name") or "").strip()
    if full:
        return full.split()[0]
    return ""


def rendering_data(payload: dict) -> dict[str, str]:
    first = first_name_from_payload(payload)
    greeting = first or "there"
    to_name = str(payload.get("to_name") or payload.get("full_name") or "").strip() or greeting
    return {
        "first_name": greeting,
        "full_name": to_name,
        "to_name": to_name,
        "company": str(payload.get("company") or ""),
        "title": str(payload.get("title") or ""),
        "offer": str(payload.get("offer") or ""),
        "icp_fact": str(payload.get("icp_fact") or ""),
    }


def render_template(template: str, data: dict) -> str:
    out = template or ""
    for key, value in data.items():
        out = out.replace("{" + key + "}", str(value) if value is not None else "")
    return out


def leftover_tokens(text: str) -> list[str]:
    return UNRENDERED_TOKEN_RE.findall(text or "")


def merge_email_copy(payload: dict) -> tuple[str, str, Optional[str]]:
    data = rendering_data(payload)
    subject = render_template(
        (payload.get("subject") or payload.get("subject_template") or "").strip(),
        data,
    ).strip()
    body = render_template(
        payload.get("body_text") or payload.get("body_template") or "",
        data,
    )
    html = payload.get("body_html")
    if html:
        html = render_template(str(html), data)
    return subject, body, html


def leftover_token_error(
    subject: str,
    body: str,
    html: Optional[str] = None,
) -> Optional[str]:
    found = leftover_tokens(subject) + leftover_tokens(body) + leftover_tokens(html or "")
    if not found:
        return None
    unique = ", ".join(sorted(set(found)))
    return f"unrendered merge tokens remain: {unique}"


def generic_boilerplate_error(
    subject: str,
    body: str,
    *,
    has_name: bool,
    has_company: bool,
    has_icp_fact: bool,
    fallback_used: bool = False,
) -> Optional[str]:
    low = f"{subject}\n{body}".lower()
    generic_hit = any(phrase in low for phrase in GENERIC_BOILERPLATE)
    if leftover_token_error(subject, body):
        return leftover_token_error(subject, body)
    if generic_hit and not has_icp_fact:
        return "generic boilerplate without a buyer-specific fact"
    if fallback_used and generic_hit:
        return "generic personalization fallback"
    if not has_name and not has_company and not has_icp_fact:
        return "copy is ungrounded: no name, company, or ICP fact"
    return None


def copy_quality_error(payload: dict) -> Optional[str]:
    subject, body, html = merge_email_copy(payload)
    token_err = leftover_token_error(subject, body, html)
    if token_err:
        return token_err
    data = rendering_data(payload)
    return generic_boilerplate_error(
        subject,
        body,
        has_name=bool(first_name_from_payload(payload)),
        has_company=bool(str(payload.get("company") or "").strip()),
        has_icp_fact=bool(str(data.get("icp_fact") or "").strip()),
        fallback_used=bool(payload.get("personalization_error") or payload.get("fallback_used")),
    )
