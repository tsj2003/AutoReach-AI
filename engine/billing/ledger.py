"""Campaign-level unit economics and margin reporting."""

from __future__ import annotations

import inspect
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

try:  # Pydantic v2
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - only used on older environments
    ConfigDict = None  # type: ignore[assignment]


class _LedgerModel(BaseModel):
    """Base schema that rejects unknown fields where supported."""

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    else:  # pragma: no cover
        class Config:
            extra = "forbid"
            arbitrary_types_allowed = True


class CostEntry(_LedgerModel):
    """Raw billing row attributed to a traced campaign operation or outcome."""

    category: str
    amount: Decimal
    trace_id: str | None = None


class PnLReport(_LedgerModel):
    """Aggregated campaign economics suitable for Cockpit dashboards."""

    total_cogs: Decimal
    total_revenue: Decimal
    gross_margin: Decimal
    breakdown: dict[str, Decimal] = Field(default_factory=dict)


class LedgerService:
    """Aggregate traced ledger rows into budget and ROI decisions."""

    REVENUE_CATEGORIES = {
        "meeting_booked",
        "meeting_qualified",
        "qualified_meeting",
        "outcome_booked",
        "outcome_qualified",
        "revenue",
    }

    def __init__(self, *, db: Any) -> None:
        self._db = db

    async def generate_pnl_report(self, *, tenant_id: str, campaign_id: str) -> PnLReport:
        entries = await self._fetch_entries(tenant_id=tenant_id, campaign_id=campaign_id)
        breakdown: dict[str, Decimal] = {}
        total_revenue = Decimal("0")
        total_cogs = Decimal("0")

        for entry in entries:
            amount = Decimal(entry.amount)
            breakdown[entry.category] = breakdown.get(entry.category, Decimal("0")) + amount
            if self._is_revenue_category(entry.category):
                total_revenue += amount
            else:
                total_cogs += amount

        return PnLReport(
            total_cogs=total_cogs,
            total_revenue=total_revenue,
            gross_margin=total_revenue - total_cogs,
            breakdown=breakdown,
        )

    async def request_spend_approval(
        self,
        *,
        tenant_id: str,
        campaign_id: str,
        requested_amount: Decimal,
        budget_limit: Decimal,
    ) -> bool:
        report = await self.generate_pnl_report(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
        )
        return report.total_cogs + Decimal(requested_amount) <= Decimal(budget_limit)

    async def _fetch_entries(self, *, tenant_id: str, campaign_id: str) -> list[CostEntry]:
        query = await self._maybe_await(self._db.query(CostEntry))
        filtered = await self._maybe_await(
            query.filter(
                ("tenant_id", tenant_id),
                ("campaign_id", campaign_id),
            )
        )
        rows = await self._maybe_await(filtered.all())
        return [self._coerce_entry(row) for row in rows]

    @classmethod
    def _is_revenue_category(cls, category: str) -> bool:
        normalized = category.strip().lower()
        return normalized in cls.REVENUE_CATEGORIES or normalized.startswith("revenue_")

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    @staticmethod
    def _coerce_entry(row: Any) -> CostEntry:
        if isinstance(row, CostEntry):
            return row
        if isinstance(row, dict):
            return CostEntry(**row)
        return CostEntry(
            category=getattr(row, "category"),
            amount=getattr(row, "amount"),
            trace_id=getattr(row, "trace_id", None),
        )
