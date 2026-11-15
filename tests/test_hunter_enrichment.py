"""Hunter enrichment provider — real client with injectable HTTP."""

from __future__ import annotations

import pytest

from engine.enrichment.models import EnrichmentRequest, VerificationStatus
from engine.enrichment.providers import HunterProvider
from engine.enrichment.waterfall import EnrichmentWaterfall


def test_hunter_not_configured_without_key():
    provider = HunterProvider(api_key="")
    assert provider.capabilities().configured is False
    result = provider.enrich(EnrichmentRequest(
        tenant_id="t1", prospect_id="p1", company_domain="acme.com", full_name="Ada Lovelace",
    ))
    assert result.success is False
    assert result.verification_status == VerificationStatus.NOT_CONFIGURED


def test_hunter_email_finder_success():
    def fake_get(url, params):
        assert "email-finder" in url
        return {"data": {"email": "ada@acme.com", "score": 92}}

    provider = HunterProvider(api_key="test-key", http_get=fake_get)
    result = provider.enrich(EnrichmentRequest(
        tenant_id="t1", prospect_id="p1", company_domain="acme.com", full_name="Ada Lovelace",
    ))
    assert result.success is True
    assert result.fields["email"] == "ada@acme.com"
    assert result.confidence >= 0.9


def test_hunter_401_is_rejected():
    def fake_get(url, params):
        raise RuntimeError("hunter 401 unauthorized")

    provider = HunterProvider(api_key="bad", http_get=fake_get)
    result = provider.enrich(EnrichmentRequest(
        tenant_id="t1", prospect_id="p1", company_domain="acme.com",
    ))
    assert result.success is False
    assert result.verification_status == VerificationStatus.REJECTED


def test_hunter_429_surface_error():
    def fake_get(url, params):
        raise RuntimeError("hunter 429 rate limited")

    provider = HunterProvider(api_key="key", http_get=fake_get)
    result = provider.enrich(EnrichmentRequest(
        tenant_id="t1", prospect_id="p1", company_domain="acme.com",
    ))
    assert result.success is False
    assert "429" in (result.error or "")


def test_waterfall_uses_hunter_when_configured():
    hunter = HunterProvider(
        api_key="k",
        http_get=lambda url, params: {"data": {"email": "ceo@acme.com", "score": 80}},
    )
    wf = EnrichmentWaterfall(providers=[hunter])
    result = wf.enrich(EnrichmentRequest(
        tenant_id="t1", prospect_id="p1", company_domain="acme.com", full_name="Ceo Person",
        required_fields=["email"],
    ))
    assert result.provider_used == "hunter"
    assert result.fields["email"] == "ceo@acme.com"


@pytest.mark.integration
def test_hunter_live_smoke_when_key_present():
    import os

    key = os.getenv("HUNTER_API_KEY", "").strip()
    if not key:
        pytest.skip("HUNTER_API_KEY not set")
    provider = HunterProvider(api_key=key)
    result = provider.enrich(EnrichmentRequest(
        tenant_id="t1", prospect_id="p1", company_domain="hunter.io", full_name="Antoine Finkelstein",
    ))
    assert result.verification_status != VerificationStatus.NOT_CONFIGURED
