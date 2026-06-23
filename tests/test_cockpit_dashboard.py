import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from decimal import Decimal
# Cursor will implement the router in cockpit/api/dashboard.py
from cockpit.main import app
from engine.billing.ledger import PnLReport

client = TestClient(app)


def test_pnl_endpoint_requires_tenant_header():
    """Forces strict tenant boundary on the financial dashboard."""
    response = client.get("/api/v1/dashboard/campaigns/cmp-123/pnl")
    assert response.status_code == 400
    assert "X-Tenant-ID header is required" in response.text


@patch("cockpit.api.dashboard.LedgerService.generate_pnl_report", new_callable=AsyncMock)
@patch("cockpit.api.dashboard.db_session")
def test_pnl_endpoint_returns_economics(mock_db, mock_generate_pnl):
    """Ensures the API correctly serializes and returns the unit economics."""
    # Setup mock return value from the ledger
    mock_generate_pnl.return_value = PnLReport(
        total_cogs=Decimal("15.50"),
        total_revenue=Decimal("1000.00"),
        gross_margin=Decimal("984.50"),
        breakdown={
            "llm_inference": Decimal("5.50"),
            "smtp_dispatch": Decimal("10.00"),
            "meeting_booked": Decimal("1000.00")
        }
    )

    response = client.get(
        "/api/v1/dashboard/campaigns/cmp-123/pnl",
        headers={"X-Tenant-ID": "t-dashboard-99"}
    )

    assert response.status_code == 200
    data = response.json()

    # Verify the ledger was called with the exact tenant and campaign
    mock_generate_pnl.assert_called_once_with(
        tenant_id="t-dashboard-99",
        campaign_id="cmp-123"
    )

    # Verify JSON serialization of Decimals handles floating point safely
    assert data["total_cogs"] == 15.50
    assert data["total_revenue"] == 1000.0
    assert data["gross_margin"] == 984.50
    assert data["breakdown"]["llm_inference"] == 5.50
