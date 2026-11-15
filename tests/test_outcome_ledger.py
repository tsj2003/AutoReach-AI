import pytest
from unittest.mock import AsyncMock, patch
from decimal import Decimal
# Cursor will expand these classes
from engine.billing.ledger import LedgerService, CostEntry, PnLReport
from engine.core.types import TenantContext


@pytest.fixture
def sample_tenant():
    return TenantContext(
        tenant_id="t-ledger-test",
        campaign_id="cmp-finance-1",
        variables={},
        encrypted_secrets={}
    )


@pytest.fixture
def mock_db_session():
    """Mocks the database query layer for ledger fetching."""
    db = AsyncMock()

    # Simulate a campaign with 10 LLM calls ($0.05 ea), 100 emails ($0.01 ea), and 2 Meetings ($1000 ea)
    def mock_query(*args, **kwargs):
        mock_chain = AsyncMock()
        mock_chain.filter.return_value.all.return_value = [
            CostEntry(category="llm_inference", amount=Decimal("0.50"), trace_id="trace-1"),
            CostEntry(category="smtp_dispatch", amount=Decimal("1.00"), trace_id="trace-2"),
            CostEntry(category="meeting_booked", amount=Decimal("2000.00"), trace_id="trace-3")
        ]
        return mock_chain

    db.query.side_effect = mock_query
    return db


@pytest.mark.asyncio
async def test_ledger_calculates_unit_economics(mock_db_session, sample_tenant):
    """
    Forces Cursor to aggregate raw entries into a PnLReport
    that calculates unit economics and margins.
    """
    ledger = LedgerService(db=mock_db_session)

    # Act: Generate the PnL report for the campaign
    report = await ledger.generate_pnl_report(
        tenant_id=sample_tenant.tenant_id,
        campaign_id=sample_tenant.campaign_id
    )

    # Assert: Cursor must build the strict PnLReport schema
    assert isinstance(report, PnLReport)

    # The total cost of operations (LLM + SMTP)
    assert report.total_cogs == Decimal("1.50")

    # The total revenue generated (Meetings)
    assert report.total_revenue == Decimal("2000.00")

    # The margin logic: Revenue - COGS
    assert report.gross_margin == Decimal("1998.50")

    # Ensure the breakdown is preserved for the frontend dashboard
    assert report.breakdown["llm_inference"] == Decimal("0.50")
    assert report.breakdown["meeting_booked"] == Decimal("2000.00")


@pytest.mark.asyncio
async def test_ledger_enforces_budget_limits(mock_db_session, sample_tenant):
    """Ensures the ledger can halt execution if COGS exceed tenant budget."""
    ledger = LedgerService(db=mock_db_session)

    # Act: Check if we can execute a $2.00 operation on a $1.00 remaining budget
    is_approved = await ledger.request_spend_approval(
        tenant_id=sample_tenant.tenant_id,
        campaign_id=sample_tenant.campaign_id,
        requested_amount=Decimal("2.00"),
        budget_limit=Decimal("1.00")
    )

    # Assert: Because total COGS is already 1.50, and budget is 1.00, it MUST reject.
    assert is_approved is False
