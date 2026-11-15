import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from decimal import Decimal

from cockpit.main import app
from engine.auth.jwt_handler import sign_jwt
from engine.billing.ledger import PnLReport

client = TestClient(app)


def _auth_header(tenant_id: str) -> dict[str, str]:
    """Mint a real signed JWT so tenant is proven, not client-asserted."""
    token = sign_jwt(
        user_id="u-1",
        tenant_id=tenant_id,
        email="owner@example.com",
        role="owner",
        plan="pro",
    )
    return {"Authorization": f"Bearer {token}"}


def test_pnl_endpoint_requires_authentication():
    """Financial data must be behind auth — no token, no access.

    Previously this endpoint trusted an X-Tenant-ID header with no auth, letting
    any caller read any tenant's P&L by guessing ids. The tenant is now derived
    from the signed JWT.
    """
    response = client.get("/api/v1/dashboard/campaigns/cmp-123/pnl")
    assert response.status_code == 401


def test_pnl_endpoint_rejects_header_spoofing():
    """A raw X-Tenant-ID header must NOT grant access without a valid token."""
    response = client.get(
        "/api/v1/dashboard/campaigns/cmp-123/pnl",
        headers={"X-Tenant-ID": "t-victim"},
    )
    assert response.status_code == 401


@patch("cockpit.api.dashboard.LedgerService.generate_pnl_report", new_callable=AsyncMock)
@patch("cockpit.api.dashboard.db_session")
def test_pnl_endpoint_uses_tenant_from_token(mock_db, mock_generate_pnl):
    """The ledger is queried with the tenant embedded in the JWT, not a header."""
    mock_generate_pnl.return_value = PnLReport(
        total_cogs=Decimal("15.50"),
        total_revenue=Decimal("1000.00"),
        gross_margin=Decimal("984.50"),
        breakdown={
            "llm_inference": Decimal("5.50"),
            "smtp_dispatch": Decimal("10.00"),
            "meeting_booked": Decimal("1000.00"),
        },
    )

    response = client.get(
        "/api/v1/dashboard/campaigns/cmp-123/pnl",
        # A spoofed header is present but must be ignored in favour of the token.
        headers={**_auth_header("t-dashboard-99"), "X-Tenant-ID": "t-attacker"},
    )

    assert response.status_code == 200
    data = response.json()

    mock_generate_pnl.assert_called_once_with(
        tenant_id="t-dashboard-99",
        campaign_id="cmp-123",
    )

    # Decimal serialization stays exact at the JSON boundary.
    assert data["total_cogs"] == 15.50
    assert data["total_revenue"] == 1000.0
    assert data["gross_margin"] == 984.50
    assert data["breakdown"]["llm_inference"] == 5.50
