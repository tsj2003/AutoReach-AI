"""OpenAI & Microsoft Azure OpenAI client — drop-in replacement for GeminiClient.

Implements `generate_json(prompt=..., ...)` returning `GeminiResult` with `GeminiUsage`
so cost accounting (`cost_breakdown_for_result`) and all callers (`website_intake`,
`personalizer`, `classifier`, etc.) work seamlessly across:
  - Standard OpenAI (`OPENAI_API_KEY`)
  - Microsoft Azure OpenAI (`AZURE_API_KEY`, `AZURE_OPENAI_ENDPOINT`,
    `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from engine.llm.gemini import (
    GeminiError,
    GeminiResult,
    GeminiUnavailable,
    GeminiUsage,
    _ssl_context,
)
import re


def _strip_code_fences(text: str) -> str:
    s = (text or '').strip()
    if s.startswith('```'):
        s = re.sub(r'^```(?:json)?\s*', '', s, flags=re.I)
        s = re.sub(r'\s*```$', '', s)
    return s.strip()

log = logging.getLogger(__name__)

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_AZURE_ENDPOINT = "https://tarandeepjuneja11-9093-resource.openai.azure.com"
DEFAULT_AZURE_DEPLOYMENT = "gpt-4o-mini"
DEFAULT_AZURE_API_VERSION = "2024-10-21"


class OpenAIClient:
    """Drop-in replacement for GeminiClient backed by OpenAI or Microsoft Azure OpenAI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_OPENAI_MODEL,
        timeout_seconds: float = 20.0,
        *,
        azure_api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        azure_deployment: Optional[str] = None,
        azure_api_version: Optional[str] = None,
        prefer_azure: bool = False,
    ) -> None:
        if api_key is not None:
            self.api_key = api_key.strip()
            # When api_key="" is explicitly passed in unit tests, do not implicitly pull AZURE_API_KEY
            self.azure_api_key = (azure_api_key or "").strip()
        else:
            self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
            self.azure_api_key = (
                azure_api_key
                if azure_api_key is not None
                else (
                    os.getenv("AZURE_API_KEY", "").strip()
                    or os.getenv("AZURE_OPENAI_API_KEY", "").strip()
                )
            )
        self.azure_endpoint = (
            azure_endpoint
            if azure_endpoint is not None
            else os.getenv("AZURE_OPENAI_ENDPOINT", DEFAULT_AZURE_ENDPOINT).strip()
        ).rstrip("/")
        self.azure_deployment = (
            azure_deployment
            if azure_deployment is not None
            else os.getenv("AZURE_OPENAI_DEPLOYMENT", DEFAULT_AZURE_DEPLOYMENT).strip()
        ) or DEFAULT_AZURE_DEPLOYMENT
        self.azure_api_version = (
            azure_api_version
            if azure_api_version is not None
            else os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_AZURE_API_VERSION).strip()
        ) or DEFAULT_AZURE_API_VERSION
        self.model = model or DEFAULT_OPENAI_MODEL
        self.timeout_seconds = timeout_seconds
        self.prefer_azure = prefer_azure or (not bool(self.api_key) and bool(self.azure_api_key))

    @property
    def is_azure_configured(self) -> bool:
        return bool(self.azure_api_key and self.azure_endpoint)

    @property
    def is_azure(self) -> bool:
        return self.is_azure_configured

    def _chat_completions_url(self) -> str:
        if self.is_azure_configured:
            return (
                f"{self.azure_endpoint}/openai/deployments/{self.azure_deployment}/chat/completions"
                f"?api-version={self.azure_api_version}"
            )
        return DEFAULT_OPENAI_URL

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key) or self.is_azure_configured

    def _build_request(
        self,
        *,
        prompt: str,
        system_instruction: Optional[str],
        temperature: float,
        max_output_tokens: int,
        use_azure: bool,
    ) -> urllib.request.Request:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.azure_deployment if use_azure else self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        data_bytes = json.dumps(payload).encode("utf-8")

        if use_azure:
            url = (
                f"{self.azure_endpoint}/openai/deployments/{self.azure_deployment}/chat/completions"
                f"?api-version={self.azure_api_version}"
            )
            headers = {
                "Content-Type": "application/json",
                "api-key": self.azure_api_key,
            }
        else:
            url = DEFAULT_OPENAI_URL
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        return urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    def generate_json(
        self,
        *,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> GeminiResult:
        if not self.has_api_key:
            raise GeminiUnavailable("Neither OPENAI_API_KEY nor AZURE_API_KEY is configured.")

        use_azure = self.prefer_azure and self.is_azure_configured
        req = self._build_request(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            use_azure=use_azure,
        )
        raw_bytes: Optional[bytes] = None
        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout_seconds, context=_ssl_context()
            ) as resp:
                raw_bytes = resp.read()
        except Exception as exc:
            # If OpenAI failed and Azure is also configured, fail over to Azure OpenAI
            if not use_azure and self.is_azure_configured:
                try:
                    azure_req = self._build_request(
                        prompt=prompt,
                        system_instruction=system_instruction,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                        use_azure=True,
                    )
                    with urllib.request.urlopen(
                        azure_req, timeout=self.timeout_seconds, context=_ssl_context()
                    ) as resp:
                        raw_bytes = resp.read()
                        use_azure = True
                except Exception as azure_exc:
                    raise GeminiError(f"OpenAI & Azure OpenAI request failed: {azure_exc}") from azure_exc
            else:
                raise GeminiError(f"OpenAI request failed: {exc}") from exc

        try:
            envelope = json.loads((raw_bytes or b"").decode("utf-8"))
            content = envelope["choices"][0]["message"]["content"]
        except Exception as exc:
            raise GeminiError(f"Invalid OpenAI response envelope: {exc}") from exc

        cleaned = _strip_code_fences(content or "")
        try:
            parsed = json.loads(cleaned)
        except Exception as exc:
            raise GeminiError(f"OpenAI returned non-JSON content: {exc}") from exc

        if not isinstance(parsed, dict):
            raise GeminiError("OpenAI JSON output must be an object/dict.")

        usage_raw = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
        p_tok = int(usage_raw.get("prompt_tokens") or 0)
        c_tok = int(usage_raw.get("completion_tokens") or 0)
        t_tok = int(usage_raw.get("total_tokens") or (p_tok + c_tok))
        usage = GeminiUsage(
            prompt_tokens=p_tok,
            output_tokens=c_tok,
            total_tokens=t_tok,
        )

        return GeminiResult(
            data=parsed,
            raw_text=content,
            model=str(envelope.get("model") or (self.azure_deployment if use_azure else self.model)),
            usage=usage,
        )


class AzureOpenAIClient(OpenAIClient):
    """Explicit Microsoft Azure OpenAI client wrapper."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("prefer_azure", True)
        super().__init__(**kwargs)
