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
On any LLM failure, subject and body are returned as the template with
{first_name} / {company} / {title} substituted from the prospect fields.
The email still sends — just generic. `fallback_used=True` is set so
the cockpit can show a yellow flag.

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

from engine.llm.gemini import GeminiClient, GeminiError, GeminiUnavailable, estimate_cost_cents

logger = logging.getLogger(__name__)

# Fields from `raw` dict that are safe to include in the Gemini prompt.
SAFE_RAW_KEYS: frozenset[str] = frozenset({
    "city", "country", "region", "industry",
    "website", "linkedin_url", "twitter_url",
    "headline", "bio",
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


def _substitute(template: str, fields: dict) -> str:
    """
    Simple {key} → value substitution. Used for fallback renders so the
    email still sends with the prospect's name/company even when Gemini fails.
    """
    out = template
    for k, v in fields.items():
        out = out.replace("{" + k + "}", str(v) if v else "")
    return out


@dataclass(frozen=True)
class PersonalizationResult:
    subject: str
    body: str
    fallback_used: bool
    error: Optional[str]
    estimated_cost_cents: int


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


_PROMPT = """\
You are writing a cold outbound email on behalf of the sender.

Sender's offer (do not change the core meaning):
{offer}

Prospect context:
  Name: {name}
  Company: {company}
  Title: {title}
  Additional context: {extra_context}

Current template subject: {subject_template}
Current template body:
{body_template}

Rewrite the subject and body using the prospect context. Rules:
- Subject: max 60 characters, lowercase or sentence case, no hype, specific to this person
- Body: max 120 words, 3 short paragraphs (opening hook / offer / CTA)
- Opening must reference something specific about the person or company
- If context fields are empty or "(unknown)", skip references — do not fake specificity
- Preserve any URLs and {{variables}} from the original templates
- No exclamation marks
- Do not say "I hope this email finds you well" or "I wanted to reach out"
- Do not invent facts, metrics, or relationships

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

    client = client or GeminiClient()
    prompt = _PROMPT.format(
        offer=offer[:800],
        name=name or "the recipient",
        company=company or "(unknown company)",
        title=title or "(unknown title)",
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

    subject_out = _cap_subject(str(result.data.get("subject") or "").strip())
    body_out = str(result.data.get("body") or "").strip()

    if not subject_out or not body_out:
        return PersonalizationResult(
            subject=subject_template, body=body_template,
            fallback_used=True,
            error="empty subject or body from gemini",
            estimated_cost_cents=estimate_cost_cents(
                prompt_chars=len(prompt), output_chars=len(result.raw_text),
            ),
        )

    return PersonalizationResult(
        subject=subject_out,
        body=body_out,
        fallback_used=False,
        error=None,
        estimated_cost_cents=estimate_cost_cents(
            prompt_chars=len(prompt), output_chars=len(result.raw_text),
        ),
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
    On fallback the returned subject/body have {first_name}/{company}/{title}
    substituted from the prospect fields so the email still reads naturally.
    """
    # Merge prospect_fields into kwargs.
    extra_context_parts: list[str] = []
    raw_used: list[str] = []

    if prospect_fields:
        name = name or str(prospect_fields.get("full_name") or "")
        company = company or str(prospect_fields.get("company") or "")
        title = title or str(prospect_fields.get("title") or "")
        raw = prospect_fields.get("raw") or {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in SAFE_RAW_KEYS and v:
                    extra_context_parts.append(f"{k}: {v}")
                    raw_used.append(k)

    if extra_context_parts and not research:
        research = "; ".join(extra_context_parts)

    # Track which meaningful fields were available.
    substitution_map = {
        "first_name": name.split()[0] if name else "",
        "full_name": name,
        "company": company,
        "title": title,
    }
    used: list[str] = [
        k for k, v in [("first_name", name), ("company", company), ("title", title)]
        if v
    ] + raw_used

    # Short-circuit: if there's no usable context even after merging, skip LLM.
    has_context = bool((name or company or research or title).strip())
    if not has_context:
        fallback_subject = _substitute(subject_template, substitution_map)
        fallback_body = _substitute(body_template, substitution_map)
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
        # Apply substitution on fallback so the email reads naturally.
        fallback_subject = _substitute(subject_template, substitution_map)
        fallback_body = _substitute(body_template, substitution_map)
        return _AgentPersonalizationResult(
            subject=fallback_subject,
            body_text=fallback_body,
            fallback_used=True,
            error=inner.error,
            estimated_cost_cents=inner.estimated_cost_cents,
            used_fields=used,
        )

    return _AgentPersonalizationResult(
        subject=inner.subject,
        body_text=inner.body,
        fallback_used=False,
        error=None,
        estimated_cost_cents=inner.estimated_cost_cents,
        used_fields=used,
    )
