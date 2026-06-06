"""
ReplyClassifier — Gemini-powered classification + draft of incoming replies.

Single public function: `classify_and_draft(...)`. Returns a typed result
the cockpit and reply-detector both consume.

Categories (closed set)
-----------------------
* interested   — wants a call/demo/pricing/more info; lead is hot
* objection    — has questions, concerns, says they're busy, "maybe later"
* unsubscribe  — explicit "no", "remove me", "stop", polite uninterest
* auto         — out-of-office / bounce / autoresponder / not a real human reply

`auto` is critical because we never want to mark a prospect as `replied`
on an autoresponder. The reply detector uses this distinction to delay
the next sequence step rather than stop it.

Failure mode
------------
If Gemini is unavailable / errors / safety-blocks, we return a
deterministic safe-default: classification='objection', empty draft,
`fallback_used=True`. The cockpit shows a yellow banner so the operator
knows they need to write the reply by hand. We never block on LLM failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from engine.llm.gemini import (
    GeminiClient,
    GeminiError,
    GeminiUnavailable,
    estimate_cost_cents,
)

logger = logging.getLogger(__name__)

VALID_CLASSIFICATIONS = ("interested", "objection", "unsubscribe", "auto")


@dataclass(frozen=True)
class ClassificationResult:
    """Returned by classify_and_draft()."""

    classification: str
    suggested_reply: str
    fallback_used: bool
    error: Optional[str]
    estimated_cost_cents: int


_PROMPT_TEMPLATE = """\
You are classifying an incoming email reply to a cold outbound message,
and drafting a short response on behalf of the sender.

Classify the reply intent into exactly one of:

  - "interested": prospect wants a call / demo / pricing / more info, OR
                  asks any genuine question that moves the conversation forward.
  - "objection":  prospect has questions, concerns, "we're busy", "send more info",
                  "maybe later", or any non-committal but-not-hostile reply.
  - "unsubscribe": prospect says "no", "remove me", "stop", "not interested",
                   "we use X already", "wrong person — please remove".
  - "auto":       out-of-office / vacation responder / bounce / autoresponder /
                  any reply that is clearly not a human typing a response.

Then draft a SHORT (max 4 sentences) suggested reply matching the classification:

  - For "interested": offer a 15-minute call and reference {{ booking_url }}
                      if it's set. Be specific, friendly, no fluff.
  - For "objection":  acknowledge their concern, address it briefly, gently
                      keep the door open. Don't beg.
  - For "unsubscribe": "Thanks for letting me know — I've removed you. Best of luck."
                       That's it. Do not pitch.
  - For "auto":       leave suggested_reply empty (""). We won't reply to bots.

Hard rules:
  - Never invent facts, names, dates, or claims.
  - Never use exclamation marks.
  - Never say you are an AI.
  - Never apologize for "reaching out" — it weakens the position.

Context:
  Original outbound subject: {original_subject}
  Original outbound body (truncated):
  --- begin original ---
  {original_body}
  --- end original ---

  Booking URL we can offer: {booking_url}

Incoming reply snippet (what we received):
  --- begin reply ---
  {snippet}
  --- end reply ---

Return STRICT JSON:
  {{
    "classification": "interested" | "objection" | "unsubscribe" | "auto",
    "suggested_reply": "string (empty for 'auto')"
  }}
"""


def classify_and_draft(
    *,
    snippet: str,
    original_subject: str = "",
    original_body: str = "",
    booking_url: str = "",
    client: Optional[GeminiClient] = None,
    temperature: float = 0.3,
) -> ClassificationResult:
    """
    Classify a reply and draft a response.

    Always returns a ClassificationResult — never raises.
    On any failure, falls back to ('objection', '', error_message) and the
    cockpit will surface that the operator needs to handle this manually.
    """
    if not snippet or not snippet.strip():
        return ClassificationResult(
            classification="objection",
            suggested_reply="",
            fallback_used=True,
            error="empty snippet",
            estimated_cost_cents=0,
        )

    client = client or GeminiClient()

    # Truncate the original body to keep prompts cheap and bounded.
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
        logger.info("Gemini unavailable; reply classifier falling back to default: %s", exc)
        return ClassificationResult(
            classification="objection",
            suggested_reply="",
            fallback_used=True,
            error=str(exc),
            estimated_cost_cents=0,
        )
    except GeminiError as exc:
        logger.warning("Gemini error during reply classification: %s", exc)
        return ClassificationResult(
            classification="objection",
            suggested_reply="",
            fallback_used=True,
            error=str(exc),
            estimated_cost_cents=0,
        )

    classification = str(result.data.get("classification") or "").strip().lower()
    if classification not in VALID_CLASSIFICATIONS:
        # The model returned something we don't accept — treat as objection
        # but flag fallback so the operator notices.
        return ClassificationResult(
            classification="objection",
            suggested_reply="",
            fallback_used=True,
            error=f"invalid classification '{classification}' from gemini",
            estimated_cost_cents=estimate_cost_cents(
                prompt_chars=len(prompt), output_chars=len(result.raw_text),
            ),
        )

    suggested = str(result.data.get("suggested_reply") or "").strip()
    if classification == "auto":
        suggested = ""  # never auto-reply to bots

    return ClassificationResult(
        classification=classification,
        suggested_reply=suggested,
        fallback_used=False,
        error=None,
        estimated_cost_cents=estimate_cost_cents(
            prompt_chars=len(prompt), output_chars=len(result.raw_text),
        ),
    )
