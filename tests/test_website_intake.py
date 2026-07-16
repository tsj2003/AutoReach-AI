"""Website → campaign config intake (the 3-minute setup)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from cockpit.main import app
from engine.auth.jwt_handler import sign_jwt
from engine.llm.gemini import GeminiResult
from engine.llm.website_intake import (
    WebsiteIntake,
    analyze_website,
    fetch_website_text,
    is_safe_fetch_url,
)

client = TestClient(app)


def _auth():
    return {"Authorization": "Bearer " + sign_jwt(
        user_id="u", tenant_id="t", email="e@x.co", role="owner", plan="pro")}


# ── SSRF guard ────────────────────────────────────────────────────────────
def test_ssrf_guard_blocks_internal_and_nonhttp():
    assert not is_safe_fetch_url("http://localhost/")
    assert not is_safe_fetch_url("http://127.0.0.1/")
    assert not is_safe_fetch_url("http://169.254.169.254/latest/meta-data/")  # cloud metadata
    assert not is_safe_fetch_url("file:///etc/passwd")
    assert not is_safe_fetch_url("http://10.0.0.5/")


def test_fetch_returns_empty_for_unsafe_url():
    assert fetch_website_text("http://127.0.0.1/") == ""


# ── analyze: LLM path + fallback ──────────────────────────────────────────
class _FakeClient:
    has_api_key = True

    def generate_json(self, *, prompt, **kw):
        return GeminiResult(
            data={
                "company_name": "Acme Deliverability",
                "summary": "Cold email infra for agencies.",
                "offer": "We help agencies run cold email without burning client domains.",
                "icp_description": "Founders of outbound agencies.",
                "client_cure": "protect client domain reputation while booking meetings.",
                "suggested_signal_types": ["funding_round", "hiring_surge"],
                "subject_template": "quick question, {first_name}",
                "body_template": "Hi {first_name}, saw {company}...",
            },
            raw_text="{}", model="gemini-2.0-flash",
        )


def test_analyze_uses_llm_when_available():
    with patch("engine.llm.website_intake.fetch_website_text", return_value="Acme sells cold email infra."):
        intake = analyze_website("https://acme.com", client=_FakeClient())
    assert intake.source == "llm"
    assert intake.company_name == "Acme Deliverability"
    assert "agencies" in intake.offer
    assert intake.suggested_signal_types == ["funding_round", "hiring_surge"]


def test_analyze_falls_back_without_llm_or_fetch():
    class _NoKey:
        has_api_key = False

        def generate_json(self, **kw):  # pragma: no cover
            raise AssertionError("should not be called without a key")

    with patch("engine.llm.website_intake.fetch_website_text", return_value=""):
        intake = analyze_website("https://newco.io", client=_NoKey())
    assert intake.source == "fallback"
    assert intake.company_name == "Newco"
    assert intake.suggested_signal_types  # sane defaults
    assert "{first_name}" in intake.subject_template


# ── endpoint: auth + wiring ───────────────────────────────────────────────
def test_endpoint_requires_auth():
    r = client.post("/api/onboarding/analyze-website", json={"url": "https://acme.com"})
    assert r.status_code == 401


def test_endpoint_returns_draft_for_authed_user():
    with patch("cockpit.api.onboarding.analyze_website") as mock:
        mock.return_value = WebsiteIntake(
            url="https://acme.com", company_name="Acme", summary="s", offer="o",
            icp_description="i", client_cure="c", suggested_signal_types=["funding_round"],
            subject_template="quick question, {first_name}", body_template="b", source="llm",
        )
        r = client.post("/api/onboarding/analyze-website", json={"url": "https://acme.com"}, headers=_auth())
    assert r.status_code == 200
    data = r.json()
    assert data["company_name"] == "Acme"
    assert data["source"] == "llm"
    assert data["suggested_signal_types"] == ["funding_round"]
