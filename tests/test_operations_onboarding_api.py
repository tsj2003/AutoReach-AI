from decimal import Decimal
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _auth_client(tmp_path):
    from cockpit import create_app

    app = create_app(db_url=f"sqlite:///{tmp_path / 'ops_api.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "ops@example.com",
            "password": "Password1!",
            "full_name": "Ops Lead",
            "company_name": "Operator Co",
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_pilot_onboarding_requires_auth(tmp_path):
    client, _ = _auth_client(tmp_path)
    response = client.post("/api/operations/pilot-onboarding", json={})
    assert response.status_code == 401


@patch("cockpit.api.operations.OnboardingService.register_tenant", new_callable=AsyncMock)
def test_pilot_onboarding_returns_preflight_status(mock_register, tmp_path):
    from cockpit.services.onboarding import TenantOnboardingResult
    from cockpit.services.preflight import PreflightResult
    from engine.runtime.context import TenantContext

    client, headers = _auth_client(tmp_path)
    mock_register.return_value = TenantOnboardingResult(
        tenant_id="tnt_pilot",
        company_name="Pilot Corp",
        domain="pilot.example",
        status="PENDING_REMEDIATION",
        preflight=PreflightResult(
            is_safe_to_send=False,
            failure_reasons=["DMARC missing"],
        ),
        tenant_context=TenantContext(
            tenant_id="tnt_pilot",
            campaign_id="pilot-onboarding",
            variables={
                "budget_limit": Decimal("5000.00"),
                "meeting_price": Decimal("1000.00"),
            },
            encrypted_secrets={},
        ),
    )

    response = client.post(
        "/api/operations/pilot-onboarding",
        headers=headers,
        json={
            "company_name": "Pilot Corp",
            "domain": "pilot.example",
            "budget_limit": "5000.00",
            "meeting_price": "1000.00",
            "linkedin_enabled": True,
            "mcp_server_command": "python",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING_REMEDIATION"
    assert data["failure_reasons"] == ["DMARC missing"]
    mock_register.assert_awaited_once()
    payload = mock_register.await_args.args[0]
    assert payload.domain == "pilot.example"
    assert payload.budget_limit == Decimal("5000.00")
