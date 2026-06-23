from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine import open_storage
from engine.core.types import CostEntry
from engine.services import OperationsService, PnLService


def _qualified_meeting(ops: OperationsService, engagement_id: str, prospect_id: str) -> None:
    meeting = ops.book_meeting(
        engagement_id=engagement_id,
        prospect_id=prospect_id,
        scheduled_for=datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc),
    )
    assert ops.update_meeting_status(meeting.id, status="qualified") is True


def test_outcome_cost_ledger_breaks_down_costs_by_category(tmp_path):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path/'ledger.db'}")
    ops = OperationsService(store=store, events=events)
    pnl = PnLService(store=store, ledger=ledger)
    eng = ops.create_engagement(
        customer_name="Acme",
        offer="Revenue ops",
        icp_description="B2B SaaS",
        price_per_outcome_cents=50_000,
    )
    p1 = ops.add_prospect(engagement_id=eng.id, email="a@example.com")
    p2 = ops.add_prospect(engagement_id=eng.id, email="b@example.com")
    _qualified_meeting(ops, eng.id, p1.id)
    _qualified_meeting(ops, eng.id, p2.id)

    ledger.debit(CostEntry(id="cost-1", engagement_id=eng.id, job_id=None, category="llm", amount_cents=300))
    ledger.debit(CostEntry(id="cost-2", engagement_id=eng.id, job_id=None, category="email_send", amount_cents=200))
    ledger.debit(CostEntry(id="cost-3", engagement_id=eng.id, job_id=None, category="enrichment", amount_cents=500))

    report = pnl.report_for(eng.id)

    assert report is not None
    assert report.cost_by_category_cents == {
        "enrichment": 500,
        "email_send": 200,
        "llm": 300,
    }
    assert report.revenue_cents == 100_000
    assert report.cost_cents == 1_000
    assert report.margin_cents == 99_000


def test_outcome_cost_ledger_unit_economics_for_qualified_outcomes(tmp_path):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path/'unit.db'}")
    ops = OperationsService(store=store, events=events)
    pnl = PnLService(store=store, ledger=ledger)
    eng = ops.create_engagement(
        customer_name="Acme",
        offer="Revenue ops",
        icp_description="B2B SaaS",
        price_per_outcome_cents=50_000,
    )
    prospect = ops.add_prospect(engagement_id=eng.id, email="ceo@example.com")
    _qualified_meeting(ops, eng.id, prospect.id)
    ledger.debit(CostEntry(id="cost-1", engagement_id=eng.id, job_id=None, category="llm", amount_cents=2_500))

    report = pnl.report_for(eng.id)

    assert report is not None
    assert report.cost_per_qualified_outcome_cents == 2_500
    assert report.profit_per_qualified_outcome_cents == 47_500


def test_outcome_cost_ledger_zero_qualified_outcomes_have_no_unit_economics(tmp_path):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path/'zero.db'}")
    ops = OperationsService(store=store, events=events)
    pnl = PnLService(store=store, ledger=ledger)
    eng = ops.create_engagement(
        customer_name="Acme",
        offer="Revenue ops",
        icp_description="B2B SaaS",
        price_per_outcome_cents=50_000,
    )
    prospect = ops.add_prospect(engagement_id=eng.id, email="ceo@example.com")
    ops.book_meeting(
        engagement_id=eng.id,
        prospect_id=prospect.id,
        scheduled_for=datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc),
    )
    ledger.debit(CostEntry(id="cost-1", engagement_id=eng.id, job_id=None, category="llm", amount_cents=2_500))

    report = pnl.report_for(eng.id)

    assert report is not None
    assert report.qualified_count == 0
    assert report.cost_per_qualified_outcome_cents is None
    assert report.profit_per_qualified_outcome_cents is None


def test_outcome_cost_ledger_tracks_budget_burn_and_overage(tmp_path):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path/'budget.db'}")
    ops = OperationsService(store=store, events=events)
    pnl = PnLService(store=store, ledger=ledger)
    eng = ops.create_engagement(
        customer_name="Acme",
        offer="Revenue ops",
        icp_description="B2B SaaS",
        monthly_budget_cents=5_000,
    )
    ledger.debit(CostEntry(id="cost-1", engagement_id=eng.id, job_id=None, category="llm", amount_cents=3_500))

    report = pnl.report_for(eng.id)

    assert report is not None
    assert report.budget_remaining_cents == 1_500
    assert report.budget_spent_pct == pytest.approx(0.7)
    assert report.over_budget is False

    ledger.debit(CostEntry(id="cost-2", engagement_id=eng.id, job_id=None, category="enrichment", amount_cents=2_000))

    over_budget_report = pnl.report_for(eng.id)
    assert over_budget_report is not None
    assert over_budget_report.budget_remaining_cents == 0
    assert over_budget_report.budget_spent_pct == pytest.approx(1.1)
    assert over_budget_report.over_budget is True
