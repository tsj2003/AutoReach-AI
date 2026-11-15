"""
AI Footprint Scrambler for AutoReach-AI.
Rewrites email structure to defeat RETVec-based bulk email detection.
Each email becomes a structurally unique piece of prose.
"""

import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


def scramble_email_structure(
    subject: str,
    body: str,
    api_key: str,
    model: str = "gemini-2.0-flash",
) -> tuple:
    """
    Rewrite email structure to defeat RETVec vector-matching.
    Changes sentence ordering, paragraph breaks, vocabulary, and flow
    while preserving the exact core offer, CTA, links, and facts.

    Args:
        subject: The email subject line.
        body: The email body text.
        api_key: Gemini API key.
        model: Gemini model to use.

    Returns:
        Tuple of (scrambled_subject, scrambled_body).
    """
    if not api_key or not body or len(body.strip()) < 20:
        return subject, body

    prompt = (
        "You are an anti-spam compliance engine. Your job is to rewrite this "
        "email to make its structure completely unique while keeping the same message.\n\n"
        "MANDATORY RULES:\n"
        "1. CHANGE: Sentence ordering, paragraph breaks, vocabulary, tone variation, "
        "greeting style, closing style\n"
        "2. PRESERVE EXACTLY: All links/URLs, email addresses, dates, names, "
        "company names, the core offer, and the call-to-action\n"
        "3. DO NOT add new facts, claims, offers, or statistics that aren't in the original\n"
        "4. Keep the email the same approximate length (within 20%)\n"
        "5. Make this email read as if a completely different person wrote it\n"
        "6. DO NOT wrap output in markdown code blocks\n\n"
        f"Subject: {subject}\n\n"
        f"Body:\n{body}\n\n"
        'Return strict JSON with keys "subject" and "body" only.'
    )

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model)}:generateContent"
        f"?key={urllib.parse.quote(api_key)}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,  # Higher temp = more structural variation
            "responseMimeType": "application/json",
        },
    }

    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))

        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

        rewritten = json.loads(text)
        new_subject = str(rewritten.get("subject") or subject).strip()
        new_body = str(rewritten.get("body") or body).strip()

        # Safety check: if the result is suspiciously short, fall back
        if len(new_body) < len(body) * 0.5:
            logger.warning("Scrambler output too short, using original")
            return subject, body

        return new_subject, new_body

    except Exception as e:
        logger.warning(f"AI Scrambler failed: {e}")
        return subject, body
