"""
Gemini outbound email personalizer.

Public entry points
-------------------
* `personalize_outbound(...)` — used by OutboundAgentV1.
* `PersonalizationResult` — frozen result type.
* `_AgentPersonalizationResult` — agent-facing result with `body_text` + `used_fields`.

Raw-field safety (reverse-targeting constraint)
----------------------------------------------
The `prospect_fields['raw']` dict may contain anything from the operator's CSV
(internal IDs, score columns, salary estimates, private notes). We MUST NOT
send arbitrary raw fields to Gemini — it exposes internal data and creates
unpredictable personalizations.

Only this explicit whitelist passes through to the LLM prompt:

    SAFE_RAW_KEYS = {city, country, region, industry, website, linkedin_url,
                     twitter_url, headline, bio}

Anything else in `raw` is silently dropped before the prompt is built.

Fallback behavior
-----------------
On any LLM failure, subject and body are the template merged with
first_name / company / title via `email_merge`. `fallback_used=True`
is set so the quality gate can refuse ungrounded generic fallbacks.

Subject length guard
--------------------
Gemini sometimes produces runaway subjects. Any subject > 80 chars is
truncated at word boundary and `fallback_used` stays False (it's just capped,
not wrong).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from engine.adapters.email_merge import merge_email_copy
from engine.llm.gemini import (
    GeminiClient,
    GeminiError,
    GeminiUnavailable,
    cost_breakdown_for_result,
)
from engine.llm.factory import build_llm_client

logger = logging.getLogger(__name__)

# Fields from `raw` dict that are safe to include in the Gemini prompt.
SAFE_RAW_KEYS: frozenset[str] = frozenset({
    "city", "country", "region", "industry",
    "website", "linkedin_url", "twitter_url",
    "headline", "bio", "first_name",
})

_MAX_SUBJECT_LEN = 80


def _cap_subject(s: str) -> str:
    """Truncate to _MAX_SUBJECT_LEN at a word boundary."""
    if len(s) <= _MAX_SUBJECT_LEN:
        return s
    truncated = s[:_MAX_SUBJECT_LEN]
    # Walk back to last space so we don't cut mid-word.
    last_space = truncated.rfind(" ")
    if last_space > 20:
        return truncated[:last_space]
    return truncated


def _merge_copy(
    *,
    subject: str,
    body: str,
    name: str = "",
    company: str = "",
    title: str = "",
    offer: str = "",
    first_name: str = "",
    icp_fact: str = "",
    raw: Optional[dict] = None,
) -> tuple[str, str]:
    """Render subject/body through the shared merge owner."""
    rendered_subject, rendered_body, _html = merge_email_copy({
        "subject": subject,
        "body_text": body,
        "first_name": first_name,
        "full_name": name,
        "to_name": name,
        "company": company,
        "title": title,
        "offer": offer,
        "icp_fact": icp_fact,
        "raw": raw if isinstance(raw, dict) else {},
    })
    return rendered_subject, rendered_body


@dataclass(frozen=True)
class PersonalizationResult:
    subject: str
    body: str
    fallback_used: bool
    error: Optional[str]
    estimated_cost_cents: int
    # Honest cost detail (see gemini.CostBreakdown). Defaults cover the fallback
    # paths where no billable LLM call was made.
    cost_basis: str = "none"
    cost_micro_usd: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class _AgentPersonalizationResult:
    """
    Agent-facing result. Has `body_text` (not `body`) and `used_fields` so
    OutboundAgentV1.plan() can read `pres.body_text` and `pres.used_fields`.
    """
    subject: str
    body_text: str
    fallback_used: bool
    error: Optional[str]
    estimated_cost_cents: int
    used_fields: list = field(default_factory=list)
    cost_basis: str = "none"
    cost_micro_usd: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0


_PROMPT = """\
You are writing a cold outbound email on behalf of the sender.

Sender's offer (do not change the core meaning):
{offer}

Prospect context:
  First name: {first_name}
  Full name: {name}
  Company: {company}
  Title: {title}
  ICP or signal fact: {icp_fact}
  Additional context: {extra_context}

Current template subject: {subject_template}
Current template body:
{body_template}

Rewrite the subject and body using the prospect context. Rules:
- Subject: max 60 characters, lowercase or sentence case, no hype, specific to this person
- Body: max 120 words, 3 short paragraphs (opening hook / offer / CTA)
- Opening must use the first name when known and one real ICP/signal/company fact
- If context fields are empty or "(unknown)", skip references — do not fake specificity
- Write finished copy. Do not leave {{first_name}} or other merge tokens in the output
- Preserve any https URLs from the original templates
- No exclamation marks
- Do not say "I hope this email finds you well" or "I wanted to reach out"
- Do not invent facts, metrics, or relationships
- Do not write generic lines like "businesses of all sizes"

Return STRICT JSON:
  {{ "subject": "...", "body": "..." }}
"""


def personalize(
    *,
    offer: str,
    name: str = "",
    company: str = "",
    title: str = "",
    research: str = "",
    subject_template: str,
    body_template: str,
    client: Optional[GeminiClient] = None,
    temperature: float = 0.45,
) -> PersonalizationResult:
    """Low-level personalizer. Never raises."""
    has_context = bool((name or company or research or title).strip())
    if not has_context:
        return PersonalizationResult(
            subject=subject_template,
            body=body_template,
            fallback_used=True,
            error="insufficient context — no name/company/title/research",
            estimated_cost_cents=0,
        )

    client = client or build_llm_client()
    first_name = name.split()[0] if name.strip() else "there"
    prompt = _PROMPT.format(
        offer=offer[:800],
        first_name=first_name,
        name=name or "the recipient",
        company=company or "(unknown company)",
        title=title or "(unknown title)",
        icp_fact=(research or "").strip()[:240] or "(none)",
        extra_context=(research or "")[:600] or "(none)",
        subject_template=subject_template,
        body_template=body_template[:1000],
    )

    try:
        result = client.generate_json(prompt=prompt, temperature=temperature)
    except GeminiUnavailable as exc:
        logger.info("Gemini unavailable; personalization fallback: %s", exc)
        return PersonalizationResult(
            subject=subject_template, body=body_template,
            fallback_used=True, error=str(exc), estimated_cost_cents=0,
        )
    except GeminiError as exc:
        logger.warning("Gemini personalization error: %s", exc)
        return PersonalizationResult(
            subject=subject_template, body=body_template,
            fallback_used=True, error=str(exc), estimated_cost_cents=0,
        )

    cb = cost_breakdown_for_result(result, prompt=prompt)
    subject_out = _cap_subject(str(result.data.get("subject") or "").strip())
    body_out = str(result.data.get("body") or "").strip()

    if not subject_out or not body_out:
        return PersonalizationResult(
            subject=subject_template, body=body_template,
            fallback_used=True,
            error="empty subject or body from gemini",
            estimated_cost_cents=cb.cents,
            cost_basis=cb.basis, cost_micro_usd=cb.micro_usd,
            prompt_tokens=cb.prompt_tokens, output_tokens=cb.output_tokens,
        )

    return PersonalizationResult(
        subject=subject_out,
        body=body_out,
        fallback_used=False,
        error=None,
        estimated_cost_cents=cb.cents,
        cost_basis=cb.basis, cost_micro_usd=cb.micro_usd,
        prompt_tokens=cb.prompt_tokens, output_tokens=cb.output_tokens,
    )


def personalize_outbound(
    *,
    offer: str = "",
    name: str = "",
    company: str = "",
    title: str = "",
    research: str = "",
    subject_template: str,
    body_template: str,
    prospect_fields: Optional[dict] = None,
    client: Optional[GeminiClient] = None,
    temperature: float = 0.45,
) -> _AgentPersonalizationResult:
    """
    Public entry point used by OutboundAgentV1 and the cockpit.

    Accepts either keyword args or a `prospect_fields` dict (or both — kwargs
    take priority). Applies the SAFE_RAW_KEYS whitelist before calling Gemini.

    Returns `_AgentPersonalizationResult` with `body_text` and `used_fields`.
    On fallback the returned subject/body are merged with first_name /
    company / title so leftover tokens do not leave this boundary.
    """
    # Merge prospect_fields into kwargs.
    extra_context_parts: list[str] = []
    raw_used: list[str] = []
    raw: dict = {}
    icp_fact = ""

    if prospect_fields:
        name = name or str(prospect_fields.get("full_name") or "")
        company = company or str(prospect_fields.get("company") or "")
        title = title or str(prospect_fields.get("title") or "")
        icp_fact = str(prospect_fields.get("icp_fact") or "").strip()
        if icp_fact:
            extra_context_parts.append(f"icp_fact: {icp_fact}")
            raw_used.append("icp_fact")
        raw = prospect_fields.get("raw") or {}
        if isinstance(raw, dict):
            explicit_first = str(raw.get("first_name") or prospect_fields.get("first_name") or "").strip()
            if explicit_first and not name:
                name = explicit_first
            for k, v in raw.items():
                if k in SAFE_RAW_KEYS and v:
                    extra_context_parts.append(f"{k}: {v}")
                    raw_used.append(k)
        else:
            raw = {}

    if extra_context_parts and not research:
        research = "; ".join(extra_context_parts)

    first_name = name.split()[0] if name else ""
    used: list[str] = [
        k for k, v in [("first_name", name), ("company", company), ("title", title)]
        if v
    ] + raw_used

    def _render(subject: str, body: str) -> tuple[str, str]:
        return _merge_copy(
            subject=subject,
            body=body,
            name=name,
            company=company,
            title=title,
            offer=offer,
            first_name=first_name,
            icp_fact=icp_fact or research,
            raw=raw,
        )

    # Short-circuit: if there's no usable context even after merging, skip LLM.
    has_context = bool((name or company or research or title).strip())
    if not has_context:
        fallback_subject, fallback_body = _render(subject_template, body_template)
        return _AgentPersonalizationResult(
            subject=fallback_subject,
            body_text=fallback_body,
            fallback_used=True,
            error="no usable context for personalization",
            estimated_cost_cents=0,
            used_fields=used,
        )

    inner = personalize(
        offer=offer,
        name=name,
        company=company,
        title=title,
        research=research,
        subject_template=subject_template,
        body_template=body_template,
        client=client,
        temperature=temperature,
    )

    if inner.fallback_used:
        fallback_subject, fallback_body = _render(subject_template, body_template)
        return _AgentPersonalizationResult(
            subject=fallback_subject,
            body_text=fallback_body,
            fallback_used=True,
            error=inner.error,
            estimated_cost_cents=inner.estimated_cost_cents,
            used_fields=used,
            cost_basis=inner.cost_basis,
            cost_micro_usd=inner.cost_micro_usd,
            prompt_tokens=inner.prompt_tokens,
            output_tokens=inner.output_tokens,
        )

    merged_subject, merged_body = _render(inner.subject, inner.body)
    return _AgentPersonalizationResult(
        subject=merged_subject,
        body_text=merged_body,
        fallback_used=False,
        error=None,
        estimated_cost_cents=inner.estimated_cost_cents,
        used_fields=used,
        cost_basis=inner.cost_basis,
        cost_micro_usd=inner.cost_micro_usd,
        prompt_tokens=inner.prompt_tokens,
        output_tokens=inner.output_tokens,
    )
