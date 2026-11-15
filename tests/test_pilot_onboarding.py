import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal
# Cursor will implement these services and models
from cockpit.services.preflight import DeliverabilityPreflight, PreflightResult
from cockpit.services.onboarding import OnboardingService, TenantOnboardingPayload


@pytest.fixture
def mock_dns_resolver():
    """Mocks DNS lookups so we don't hit real networks during unit tests."""
    with patch("cockpit.services.preflight.dns.asyncresolver.resolve", new_callable=AsyncMock) as mock_resolve:
        yield mock_resolve


@pytest.mark.asyncio
async def test_preflight_fails_missing_dmarc(mock_dns_resolver):
    """Forces the preflight to fail closed if DMARC is missing (crucial for Google sender rules)."""
    # Simulate SPF passes, but DMARC throws an exception/fails
    async def mock_resolve_side_effect(qname, rdtype):
        if rdtype == 'TXT' and not qname.startswith('_dmarc'):
            mock_record = MagicMock()
            mock_record.strings = [b"v=spf1 include:_spf.google.com ~all"]
            return [mock_record]
        raise Exception("DNS query failed") # Simulating no DMARC record

    mock_dns_resolver.side_effect = mock_resolve_side_effect

    preflight = DeliverabilityPreflight()
    result = await preflight.verify_domain("unprepared-startup.com")

    # Assert: Must return a strictly typed PreflightResult marking it unsafe
    assert isinstance(result, PreflightResult)
    assert result.is_safe_to_send is False
    assert "DMARC missing" in result.failure_reasons


@pytest.mark.asyncio
@patch("cockpit.services.onboarding.db_session")
@patch("cockpit.services.preflight.DeliverabilityPreflight.verify_domain", new_callable=AsyncMock)
async def test_onboarding_wizard_blocks_unsafe_tenants(mock_verify, mock_db):
    """Ensures the onboarding service will not activate a tenant if preflight fails."""
    # Simulate a failed preflight
    mock_verify.return_value = PreflightResult(is_safe_to_send=False, failure_reasons=["SPF missing"])

    onboarding = OnboardingService()
    payload = TenantOnboardingPayload(
        company_name="Acme Corp",
        domain="acme-outbound.com",
        budget_limit=Decimal("5000.00"),
        meeting_price=Decimal("1000.00"),
        linkedin_enabled=True,
        mcp_server_command="python"
    )

    result = await onboarding.register_tenant(payload)

    # Assert: Tenant is created so we don't lose the data, but status MUST be PENDING_REMEDIATION
    assert result.status == "PENDING_REMEDIATION"
    mock_db.commit.assert_called_once() # Saves the pending state


@pytest.mark.asyncio
@patch("cockpit.services.onboarding.db_session")
@patch("cockpit.services.preflight.DeliverabilityPreflight.verify_domain", new_callable=AsyncMock)
async def test_onboarding_wizard_activates_safe_tenants(mock_verify, mock_db):
    """Ensures a fully configured, preflight-passing tenant goes live immediately."""
    mock_verify.return_value = PreflightResult(is_safe_to_send=True, failure_reasons=[])

    onboarding = OnboardingService()
    payload = TenantOnboardingPayload(
        company_name="Solid Corp",
        domain="solid-outbound.com",
        budget_limit=Decimal("5000.00"),
        meeting_price=Decimal("1000.00"),
        linkedin_enabled=False
    )

    result = await onboarding.register_tenant(payload)

    # Assert: Passed preflight, so it gets the green light
    assert result.status == "ACTIVE"
    # Ensure financial metrics were initialized
    assert result.tenant_context.variables["budget_limit"] == Decimal("5000.00")
