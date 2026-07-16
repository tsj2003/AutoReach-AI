"""Optional LLM critic for the Deliverability Guardian.

The deterministic Guardian catches known spam triggers and AI tells. This adds a
model's judgment — "does this read machine-generated, and what would a human
change?" — which is exactly the signal 2026 filters penalize. Provider-agnostic
by design; ships with an OpenAI-backed critic (uses OPENAI_API_KEY from the
environment, e.g. your local .env) and degrades to no-op when unconfigured or on
any error, so it can never break send planning.

Dependency-free (stdlib urllib), mirroring GeminiClient. Never logs the key.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Callable, Optional, Sequence

from engine.llm.gemini import _ssl_context
from engine.services.deliverability_guardian import RiskIssue

logger = logging.getLogger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_DEFAULT_MODEL = "gpt-4o-mini"

_SYSTEM = (
    "You are an elite cold-email deliverability and spam-filter expert. Given a "
    "cold email, flag anything that (a) reads AI-generated/templated or (b) would "
    "trip spam filters or hurt inbox placement. Be terse and concrete."
)


def _prompt(subject: str, body: str) -> str:
    return (
        f"SUBJECT: {subject}\n\nBODY:\n{body}\n\n"
        'Return STRICT JSON: {"issues":[{"detail":"...","fix":"...",'
        '"severity":"low|medium|high"}]}. Empty array if it reads human and clean.'
    )


def openai_email_critic(
    subject: str,
    body: str,
    *,
    api_key: Optional[str] = None,
    model: str = _DEFAULT_MODEL,
    timeout: int = 15,
) -> Sequence[RiskIssue]:
    """Return LLM-identified risk issues. Never raises — returns [] on any problem."""
    key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
    if not key:
        return []
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _prompt(subject or "", body or "")},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    try:
        req = urllib.request.Request(
            _OPENAI_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        data = json.loads(content)
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
        logger.info("AI critic unavailable (non-fatal): %s", type(exc).__name__)
        return []

    issues: list[RiskIssue] = []
    for item in (data.get("issues") or [])[:8]:
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity", "medium")).lower()
        if sev not in {"low", "medium", "high"}:
            sev = "medium"
        issues.append(RiskIssue(
            code="ai_critic",
            severity=sev,
            detail=str(item.get("detail", "LLM flagged risk"))[:300],
            fix=str(item.get("fix", "Revise by hand."))[:300],
        ))
    return issues


def build_ai_critic() -> Optional[Callable[[str, str], Sequence[RiskIssue]]]:
    """Return an OpenAI critic when OPENAI_API_KEY is set, else None (deterministic-only)."""
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return None
    return openai_email_critic
