"""DKIM is surfaced as a non-blocking warning (selector-specific → can't hard-fail)."""

from __future__ import annotations

import pytest

from cockpit.services.preflight import DeliverabilityPreflight


class _FakePreflight(DeliverabilityPreflight):
    def __init__(self, txt_by_name):
        self._txt = txt_by_name

    async def _lookup_txt(self, qname):
        return self._txt.get(qname, [])


@pytest.mark.asyncio
async def test_dkim_missing_is_a_warning_not_a_block():
    pf = _FakePreflight({
        "acme.com": ["v=spf1 include:_spf.google.com ~all"],
        "_dmarc.acme.com": ["v=DMARC1; p=quarantine"],
        # no *_domainkey records → DKIM undetected
    })
    result = await pf.verify_domain("acme.com")
    assert result.is_safe_to_send is True          # SPF + DMARC present → not blocked
    assert result.failure_reasons == []
    assert any("DKIM" in w for w in result.warnings)  # but flagged


@pytest.mark.asyncio
async def test_dkim_present_produces_no_warning():
    pf = _FakePreflight({
        "acme.com": ["v=spf1 include:_spf.google.com ~all"],
        "_dmarc.acme.com": ["v=DMARC1; p=reject"],
        "google._domainkey.acme.com": ["v=DKIM1; k=rsa; p=MIGf..."],
    })
    result = await pf.verify_domain("acme.com")
    assert result.is_safe_to_send is True
    assert result.warnings == []
