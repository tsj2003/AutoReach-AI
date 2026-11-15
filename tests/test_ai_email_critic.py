"""OpenAI-backed LLM critic for the Guardian — env-gated, fail-safe."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

from engine.services.ai_email_critic import build_ai_critic, openai_email_critic
from engine.services.deliverability_guardian import DeliverabilityGuardian, RiskIssue


def test_critic_is_noop_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert build_ai_critic() is None
    assert openai_email_critic("s", "b") == []  # no key → no-op, never raises


def test_build_ai_critic_active_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert build_ai_critic() is not None


def _fake_openai_response(issues):
    body = json.dumps({
        "choices": [{"message": {"content": json.dumps({"issues": issues})}}]
    }).encode("utf-8")

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return _Resp(body)


def test_critic_parses_llm_issues(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake = _fake_openai_response([
        {"detail": "Opening reads AI-generated", "fix": "Rewrite by hand", "severity": "high"},
    ])
    with patch("urllib.request.urlopen", return_value=fake):
        issues = openai_email_critic("hi", "I hope this email finds you well.")
    assert len(issues) == 1
    assert issues[0].code == "ai_critic"
    assert issues[0].severity == "high"


def test_critic_failure_is_swallowed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        assert openai_email_critic("hi", "body") == []  # never breaks planning


def test_guardian_uses_injected_critic():
    def critic(subject, body):
        return [RiskIssue("ai_critic", "high", "LLM says generated", "Rewrite")]

    r = DeliverabilityGuardian(llm_critic=critic).score(subject="hi", body="short human note")
    assert any(i.code == "ai_critic" for i in r.issues)
