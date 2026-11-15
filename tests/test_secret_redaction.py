"""Secret redaction regression tests."""

from __future__ import annotations

from engine.security.redact import redact_dict, redact_string


def test_redact_bearer_token():
    assert "Bearer ***" in redact_string("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.xxx")


def test_redact_webhook_secret_in_dict():
    out = redact_dict({"webhook_secret": "abc123", "name": "source"})
    assert out["webhook_secret"] == "***"
    assert out["name"] == "source"


def test_redact_api_key_pattern():
    assert "***" in redact_string("api_key=sk-live-abcdef123456")
