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
import math
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


def _ssl_context() -> Optional[ssl.SSLContext]:
    """Verified TLS context using certifi's CA bundle when present.

    The stdlib default relies on the OS trust store, which is missing on some
    Python installs (notably macOS Python.framework) and would fail cert
    verification. Falling back to certifi keeps real Gemini calls working in dev
    and any cert-less environment; returns None (stdlib default) if certifi
    isn't installed. We never disable verification.
    """
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # pragma: no cover - depends on env
        return None

DEFAULT_MODEL = "gemini-2.0-flash"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(RuntimeError):
    """Raised when the Gemini API call fails or returns malformed JSON."""


class GeminiUnavailable(GeminiError):
    """Raised when no API key is configured (treat as non-fatal at the caller)."""


@dataclass(frozen=True)
class GeminiUsage:
    """Real token accounting from the API's usageMetadata."""

    prompt_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass
class GeminiResult:
    """The decoded JSON object from a structured-output Gemini call."""

    data: dict
    raw_text: str
    model: str
    usage: Optional[GeminiUsage] = None


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
            with urllib.request.urlopen(
                req, timeout=self._timeout, context=_ssl_context()
            ) as response:
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

        usage = None
        meta = response_data.get("usageMetadata")
        if isinstance(meta, dict):
            usage = GeminiUsage(
                prompt_tokens=int(meta.get("promptTokenCount", 0) or 0),
                output_tokens=int(meta.get("candidatesTokenCount", 0) or 0),
                total_tokens=int(meta.get("totalTokenCount", 0) or 0),
            )

        return GeminiResult(data=decoded, raw_text=text, model=chosen_model, usage=usage)


# Gemini token pricing in USD per 1M TOKENS (not chars). Published rates for
# gemini-2.0-flash as of Jan 2026 — update when Google changes pricing.
_MODEL_TOKEN_PRICING_USD_PER_M: dict[str, tuple[float, float]] = {
    "gemini-2.0-flash": (0.10, 0.40),  # (input, output)
}
_DEFAULT_TOKEN_PRICING_USD_PER_M = (0.10, 0.40)
_MICRO_USD_PER_CENT = 10_000  # 1 cent = $0.01 = 10,000 micro-USD


@dataclass(frozen=True)
class CostBreakdown:
    """Cost of a single LLM call.

    `micro_usd` (millionths of a dollar) is the PRECISE source of truth and is
    stamped into the ledger entry's metadata. `cents` is a coarse, conservative
    view for the integer-cents ledger column: any non-zero cost rounds UP to at
    least 1 cent, so per-call cents can overstate sub-cent calls — read
    `cost_micro_usd` from metadata for accurate aggregate COGS.
    """

    cents: int
    micro_usd: int
    basis: str  # "actual_tokens" | "estimated_chars"
    prompt_tokens: int
    output_tokens: int
    model: str

    def as_metadata(self) -> dict:
        return {
            "cost_basis": self.basis,
            "cost_micro_usd": self.micro_usd,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "model": self.model,
        }


def _micro_usd_from_tokens(prompt_tokens: int, output_tokens: int, model: str) -> int:
    in_rate, out_rate = _MODEL_TOKEN_PRICING_USD_PER_M.get(model, _DEFAULT_TOKEN_PRICING_USD_PER_M)
    usd = (prompt_tokens * in_rate + output_tokens * out_rate) / 1_000_000
    return int(round(usd * 1_000_000))


def _micro_usd_from_chars(prompt_chars: int, output_chars: int) -> int:
    # Legacy char-based proxy used only when the API reports no token usage.
    usd = (prompt_chars * 0.075 + output_chars * 0.30) / 1_000_000
    return int(round(usd * 1_000_000))


def _cents_from_micro_usd(micro_usd: int) -> int:
    if micro_usd <= 0:
        return 0
    return max(1, math.ceil(micro_usd / _MICRO_USD_PER_CENT))


def cost_breakdown_for_result(result: GeminiResult, *, prompt: str) -> CostBreakdown:
    """Real token-based cost when the API reported usage; char estimate otherwise."""
    if result.usage is not None and result.usage.total_tokens > 0:
        micro = _micro_usd_from_tokens(
            result.usage.prompt_tokens, result.usage.output_tokens, result.model
        )
        return CostBreakdown(
            cents=_cents_from_micro_usd(micro),
            micro_usd=micro,
            basis="actual_tokens",
            prompt_tokens=result.usage.prompt_tokens,
            output_tokens=result.usage.output_tokens,
            model=result.model,
        )
    micro = _micro_usd_from_chars(len(prompt), len(result.raw_text))
    return CostBreakdown(
        cents=_cents_from_micro_usd(micro),
        micro_usd=micro,
        basis="estimated_chars",
        prompt_tokens=0,
        output_tokens=0,
        model=result.model,
    )


def estimate_cost_cents(
    *,
    prompt_chars: int,
    output_chars: int,
    model: str = DEFAULT_MODEL,
) -> int:
    """Char-based cost estimate in cents (conservative fallback for budgeting)."""
    return _cents_from_micro_usd(_micro_usd_from_chars(prompt_chars, output_chars))
