"""
PnLService — per-engagement profit & loss for OaaS billing.

Revenue rule (OaaS)
-------------------
Only `qualified` meetings count toward revenue. `booked` meetings are
*pipeline*; `no_show` and `cancelled` produce zero revenue and zero
clawback (we ate the cost). This rule is applied in one place so the
cockpit, CLI, and future invoicing all agree.

Cost rule
---------
All entries in the cost ledger for the Engagement count, regardless of
category. The category breakdown is shown for diagnostics, not for billing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from engine.core.protocols import CostLedger, Store
from engine.core.types import Engagement


@dataclass(frozen=True)
class PnLReport:
    """A read-only snapshot of an Engagement's economics."""

    engagement_id: str
    customer_name: str
    monthly_meeting_target: int | None
    price_per_outcome_cents: int | None
    monthly_budget_cents: int | None
    # Pipeline
    booked_count: int
    qualified_count: int
    no_show_count: int
    cancelled_count: int
    # Money (all integer cents)
    revenue_cents: int
    cost_cents: int
    margin_cents: int
    margin_pct: float  # 0..1 of revenue, or 0.0 if revenue is 0

    @property
    def revenue_dollars(self) -> float:
        return self.revenue_cents / 100.0

    @property
    def cost_dollars(self) -> float:
        return self.cost_cents / 100.0

    @property
    def margin_dollars(self) -> float:
        return self.margin_cents / 100.0


class PnLService:
    """Compute per-engagement P&L from store + ledger state."""

    def __init__(self, *, store: Store, ledger: CostLedger) -> None:
        self._store = store
        self._ledger = ledger

    def report_for(self, engagement_id: str) -> PnLReport | None:
        eng: Engagement | None = self._store.get_engagement(engagement_id)
        if eng is None:
            return None

        meetings = list(self._store.list_meetings(engagement_id, limit=10_000))
        booked = sum(1 for m in meetings if m.status == "booked")
        qualified = sum(1 for m in meetings if m.status == "qualified")
        no_show = sum(1 for m in meetings if m.status == "no_show")
        cancelled = sum(1 for m in meetings if m.status == "cancelled")

        price = eng.price_per_outcome_cents or 0
        revenue = qualified * price

        cost = self._ledger.total_spent_cents(engagement_id)
        margin = revenue - cost
        margin_pct = (margin / revenue) if revenue > 0 else 0.0

        return PnLReport(
            engagement_id=eng.id,
            customer_name=eng.customer_name,
            monthly_meeting_target=eng.monthly_meeting_target,
            price_per_outcome_cents=eng.price_per_outcome_cents,
            monthly_budget_cents=eng.monthly_budget_cents,
            booked_count=booked,
            qualified_count=qualified,
            no_show_count=no_show,
            cancelled_count=cancelled,
            revenue_cents=revenue,
            cost_cents=cost,
            margin_cents=margin,
            margin_pct=margin_pct,
        )

    def report_all(self) -> Iterable[PnLReport]:
        for eng in self._store.list_engagements():
            r = self.report_for(eng.id)
            if r is not None:
                yield r
