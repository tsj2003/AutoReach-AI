"""OpenAIClient is a drop-in for GeminiClient; factory prefers OpenAI when keyed."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from engine.llm.gemini import GeminiError, GeminiUnavailable, cost_breakdown_for_result
from engine.llm.openai_client import OpenAIClient
from engine.llm.factory import build_llm_client


def _fake_response(content: str, usage: dict | None = None):
    body = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        body["usage"] = usage
    raw = json.dumps(body).encode("utf-8")

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return _Resp(raw)


def test_no_key_raises_unavailable():
    c = OpenAIClient(api_key="")
    with pytest.raises(GeminiUnavailable):
        c.generate_json(prompt="hi")


def test_generate_json_parses_and_maps_usage():
    c = OpenAIClient(api_key="sk-test")
    fake = _fake_response('{"subject":"hi","body":"there"}',
                          usage={"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500})
    with patch("urllib.request.urlopen", return_value=fake):
        r = c.generate_json(prompt="write JSON")
    assert r.data == {"subject": "hi", "body": "there"}
    assert r.model == "gpt-4o-mini"
    assert r.usage.prompt_tokens == 1000
    assert r.usage.output_tokens == 500  # completion_tokens → output_tokens
    # cost accounting works with real tokens + gpt-4o-mini pricing.
    cb = cost_breakdown_for_result(r, prompt="x")
    assert cb.basis == "actual_tokens"
    # 1000*0.15/1e6 + 500*0.60/1e6 = 0.00015 + 0.0003 = 0.00045 USD = 450 micro-USD
    assert cb.micro_usd == 450


def test_http_error_raises_gemini_error():
    c = OpenAIClient(api_key="sk-test")
    with patch("urllib.request.urlopen", side_effect=OSError("boom")):
        with pytest.raises(GeminiError):
            c.generate_json(prompt="hi")


def test_non_object_output_raises():
    c = OpenAIClient(api_key="sk-test")
    with patch("urllib.request.urlopen", return_value=_fake_response('[1,2,3]', usage={})):
        with pytest.raises(GeminiError):
            c.generate_json(prompt="hi")


def test_factory_prefers_openai_when_keyed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert isinstance(build_llm_client(), OpenAIClient)


def test_factory_falls_back_to_gemini_without_openai(monkeypatch):
    from engine.llm.gemini import GeminiClient
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert isinstance(build_llm_client(), GeminiClient)
