"""
ReplyClassifier — Gemini-powered classification + draft of incoming replies.

Single public function: `classify_and_draft(...)`. Returns a typed result the
cockpit, reply-detector, and ReplyActionExecutor consume.

Categories (closed set)
-----------------------
* interested      — wants a call/demo/pricing/more info; lead is hot
* objection       — questions, concerns, "we're busy", "maybe later"
* not_interested  — soft no, "not a fit right now", but not hostile/opt-out
* out_of_office   — vacation/OOO responder; we extract a return date and
                    reschedule the follow-up rather than stop it
* referral        — "talk to <someone else>"; we extract the referred contact
* do_not_contact  — hard opt-out / "remove me" / legal-toned; unsubscribe + blocklist
* unsubscribe     — explicit opt-out (kept for backward compat; treated like DNC)
* auto            — bounce / autoresponder that is NOT an OOO (e.g. mailer-daemon)

Extra extracted fields (best-effort, may be empty):
* return_date     — ISO date string for out_of_office
* referred_email  — email address for referral
* referred_name   — name for referral

Failure mode
------------
Any Gemini failure → safe default: ('objection', '', fallback_used=True).
Never raises, never blocks the pipeline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from engine.llm.gemini import (
    GeminiClient,
    GeminiError,
    GeminiUnavailable,
    estimate_cost_cents,
)

logger = logging.getLogger(__name__)

VALID_CLASSIFICATIONS = (
    "interested",
    "objection",
    "not_interested",
    "out_of_office",
    "referral",
    "do_not_contact",
    "unsubscribe",   # legacy alias for do_not_contact
    "auto",
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


@dataclass(frozen=True)
class ClassificationResult:
    """Returned by classify_and_draft()."""

    classification: str
    suggested_reply: str
    fallback_used: bool
    error: Optional[str]
    estimated_cost_cents: int
    # Best-effort extracted structured data (may be empty).
    return_date: Optional[str] = None          # ISO date for out_of_office
    referred_email: Optional[str] = None        # for referral
    referred_name: Optional[str] = None         # for referral


_PROMPT_TEMPLATE = """\
You classify an incoming email reply to a cold outbound message and draft a
short response on behalf of the sender.

Classify into exactly one of:
  - "interested":     wants a call/demo/pricing/more info, or asks a genuine
                      forward-moving question.
  - "objection":      has concerns/questions, "we're busy", "send info", "maybe later".
  - "not_interested": soft no — "not a fit", "not right now" — polite, not hostile.
  - "out_of_office":  vacation / OOO auto-reply from a human's mailbox. If a
                      return date is mentioned, extract it as ISO (YYYY-MM-DD).
  - "referral":       points you to a different person ("talk to Jane", "loop in
                      our CTO"). Extract the referred person's email and/or name.
  - "do_not_contact": hard opt-out — "remove me", "stop", "unsubscribe", legal tone.
  - "auto":           bounce / mailer-daemon / non-OOO autoresponder.

Draft a SHORT (max 4 sentences) suggested_reply:
  - interested:     offer a 15-minute call, reference {booking_url} if set.
  - objection:      acknowledge briefly, keep the door open, don't beg.
  - not_interested: "Understood — thanks for the reply. I'll close the loop here."
  - out_of_office:  leave empty ("") — we just reschedule.
  - referral:       brief, gracious; ask for a warm intro to the referred person.
  - do_not_contact: "Thanks for letting me know — I've removed you. Best of luck."
  - auto:           leave empty ("").

Hard rules: never invent facts, no exclamation marks, never say you're an AI,
never apologize for reaching out.

Context:
  Original subject: {original_subject}
  Original body (truncated): {original_body}
  Booking URL: {booking_url}

Incoming reply:
  {snippet}

Return STRICT JSON:
  {{
    "classification": "<one of the categories above>",
    "suggested_reply": "string",
    "return_date": "YYYY-MM-DD or empty",
    "referred_email": "email or empty",
    "referred_name": "name or empty"
  }}
"""


def _fallback(error: str, cost: int = 0) -> ClassificationResult:
    return ClassificationResult(
        classification="objection",
        suggested_reply="",
        fallback_used=True,
        error=error,
        estimated_cost_cents=cost,
    )


def classify_and_draft(
    *,
    snippet: str,
    original_subject: str = "",
    original_body: str = "",
    booking_url: str = "",
    client: Optional[GeminiClient] = None,
    temperature: float = 0.3,
) -> ClassificationResult:
    """Classify a reply + draft a response. Never raises."""
    if not snippet or not snippet.strip():
        return _fallback("empty snippet")

    client = client or GeminiClient()
    original_body = (original_body or "")[:1200]
    snippet = snippet[:1500]

    prompt = _PROMPT_TEMPLATE.format(
        original_subject=original_subject or "(unknown)",
        original_body=original_body or "(unavailable)",
        booking_url=booking_url or "(none configured)",
        snippet=snippet,
    )

    try:
        result = client.generate_json(prompt=prompt, temperature=temperature)
    except GeminiUnavailable as exc:
        logger.info("Gemini unavailable; classifier fallback: %s", exc)
        return _fallback(str(exc))
    except GeminiError as exc:
        logger.warning("Gemini error during classification: %s", exc)
        return _fallback(str(exc))

    cost = estimate_cost_cents(prompt_chars=len(prompt), output_chars=len(result.raw_text))
    classification = str(result.data.get("classification") or "").strip().lower()
    if classification not in VALID_CLASSIFICATIONS:
        return _fallback(f"invalid classification '{classification}' from gemini", cost)

    suggested = str(result.data.get("suggested_reply") or "").strip()
    if classification in ("auto", "out_of_office"):
        suggested = ""  # never auto-reply to bots / OOO

    # Best-effort structured extraction with regex backstops.
    return_date = (str(result.data.get("return_date") or "").strip() or None)
    if classification == "out_of_office" and not return_date:
        m = _ISO_DATE_RE.search(snippet)
        return_date = m.group(1) if m else None

    referred_email = (str(result.data.get("referred_email") or "").strip() or None)
    if classification == "referral" and not referred_email:
        m = _EMAIL_RE.search(snippet)
        referred_email = m.group(0) if m else None
    referred_name = (str(result.data.get("referred_name") or "").strip() or None)

    return ClassificationResult(
        classification=classification,
        suggested_reply=suggested,
        fallback_used=False,
        error=None,
        estimated_cost_cents=cost,
        return_date=return_date if classification == "out_of_office" else None,
        referred_email=referred_email if classification == "referral" else None,
        referred_name=referred_name if classification == "referral" else None,
    )
