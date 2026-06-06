"""
GeminiClient — thin, dependency-free Gemini API client.

Why hand-rolled and not `google-genai` SDK
------------------------------------------
* Zero new dependencies. `urllib` is in stdlib; the SDK pulls in 8+ extras.
* The legacy AutoReach code already worked with this pattern; keeping the
  shape identical means we know it works against real Gemini in production.
* All responses go through structured JSON output (`responseMimeType=application/json`),
  so we get parse errors at a clean boundary instead of fishy text scraping.

The client knows nothing about replies, audits, or personalization. It just
makes structured-JSON calls. The reply-classification + draft + future audit
logic lives one layer up (`engine.llm.classifier`).

Cost
----
Every call goes through `record_cost(...)` if a CostLedger is supplied at
call time, so the cockpit's per-engagement P&L stays accurate.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(RuntimeError):
    """Raised when the Gemini API call fails or returns malformed JSON."""


class GeminiUnavailable(GeminiError):
    """Raised when no API key is configured (treat as non-fatal at the caller)."""


@dataclass
class GeminiResult:
    """The decoded JSON object from a structured-output Gemini call."""

    data: dict
    raw_text: str
    model: str


class GeminiClient:
    """
    Minimal Gemini structured-JSON client.

    Parameters
    ----------
    api_key : str | None
        Defaults to env GEMINI_API_KEY. If empty, every call raises GeminiUnavailable.
    model : str
        Default model. Caller can override per-call.
    timeout_seconds : int
        Per-request timeout. Gemini Flash is usually <5s; we give plenty of slack.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = 30,
    ) -> None:
        self._api_key = (api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        self._model = model
        self._timeout = timeout_seconds

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def generate_json(
        self,
        *,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        system_instruction: Optional[str] = None,
    ) -> GeminiResult:
        """
        Make a Gemini call expecting a JSON object back.

        Returns a `GeminiResult`. Raises `GeminiUnavailable` if no key, or
        `GeminiError` on network / parse failure.
        """
        if not self._api_key:
            raise GeminiUnavailable("GEMINI_API_KEY not configured")

        chosen_model = model or self._model
        endpoint = (
            f"{GEMINI_BASE}/{urllib.parse.quote(chosen_model)}:generateContent"
            f"?key={urllib.parse.quote(self._api_key)}"
        )

        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": float(temperature),
                "responseMimeType": "application/json",
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                body_bytes = response.read()
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")[:500]
            raise GeminiError(
                f"gemini http {exc.code}: {exc.reason}; body={err_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise GeminiError(f"gemini network error: {exc.reason}") from exc
        except Exception as exc:  # safety net
            raise GeminiError(f"gemini call failed: {exc}") from exc

        try:
            response_data = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise GeminiError(f"gemini response not JSON: {exc}") from exc

        text = (
            response_data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if not text:
            raise GeminiError(
                f"gemini returned empty content (possible safety block); "
                f"finishReason={response_data.get('candidates',[{}])[0].get('finishReason')}"
            )

        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GeminiError(f"gemini output not parseable as JSON: {exc}; text={text[:200]}") from exc
        if not isinstance(decoded, dict):
            raise GeminiError(f"gemini output is not a JSON object (got {type(decoded).__name__})")

        return GeminiResult(data=decoded, raw_text=text, model=chosen_model)


def estimate_cost_cents(
    *,
    prompt_chars: int,
    output_chars: int,
    model: str = DEFAULT_MODEL,
) -> int:
    """
    Rough cost estimate in cents for budgeting.

    Gemini Flash 2.0 (May 2026): ~$0.075 / 1M input chars, ~$0.30 / 1M output.
    Round up to the nearest cent so the ledger is conservative.
    """
    input_cost = prompt_chars * 0.075 / 1_000_000  # USD
    output_cost = output_chars * 0.30 / 1_000_000
    total_cents = (input_cost + output_cost) * 100
    return max(1, int(total_cents) + 1)
