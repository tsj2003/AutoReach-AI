"""Tenant-scoped ROI dashboard API."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from engine.auth.jwt_bearer import get_current_user_dep
from engine.auth.models import CurrentUser
from engine.billing.ledger import CostEntry, LedgerService, PnLReport

db_session: Any = None

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


async def require_tenant_id(user: CurrentUser = Depends(get_current_user_dep)) -> str:
    """Resolve tenant from the signed JWT — never from a client-supplied header.

    Financial data must be bound to the authenticated identity. Trusting an
    ``X-Tenant-ID`` header here previously let any caller read any tenant's P&L
    by guessing a tenant/campaign id.
    """
    return user.tenant_id


def _session(request: Request) -> Any:
    if db_session is not None:
        return db_session
    pnl = getattr(request.app.state, "pnl", None)
    store = getattr(request.app.state, "store", None)
    if pnl is None or store is None:
        raise HTTPException(status_code=503, detail="Dashboard database is not configured")
    return _CockpitLedgerSession(pnl=pnl, store=store)


@router.get("/campaigns/{campaign_id}/pnl")
async def campaign_pnl(
    request: Request,
    campaign_id: str,
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, Any]:
    report = await LedgerService(db=_session(request)).generate_pnl_report(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    return _pnl_report_to_json(report)


def _pnl_report_to_json(report: PnLReport) -> dict[str, Any]:
    return {
        "total_cogs": _decimal_to_float(report.total_cogs),
        "total_revenue": _decimal_to_float(report.total_revenue),
        "gross_margin": _decimal_to_float(report.gross_margin),
        "breakdown": {
            category: _decimal_to_float(amount)
            for category, amount in report.breakdown.items()
        },
    }


def _decimal_to_float(value: Decimal) -> float:
    return float(value)


class _CockpitLedgerSession:
    """Small query adapter from the engine PnL service to billing ledger rows."""

    def __init__(self, *, pnl: Any, store: Any) -> None:
        self._pnl = pnl
        self._store = store

    def query(self, model: type[CostEntry]) -> "_CockpitLedgerQuery":
        return _CockpitLedgerQuery(pnl=self._pnl, store=self._store)


class _CockpitLedgerQuery:
    def __init__(self, *, pnl: Any, store: Any) -> None:
        self._pnl = pnl
        self._store = store
        self._tenant_id: str | None = None
        self._campaign_id: str | None = None

    def filter(self, *conditions: Any) -> "_CockpitLedgerQuery":
        for condition in conditions:
            if isinstance(condition, tuple) and len(condition) == 2:
                key, value = condition
                if key == "tenant_id":
                    self._tenant_id = value
                elif key == "campaign_id":
                    self._campaign_id = value
        return self

    def all(self) -> list[CostEntry]:
        if not self._tenant_id or not self._campaign_id:
            return []
        if self._store.get_engagement(self._campaign_id, tenant_id=self._tenant_id) is None:
            return []

        report = self._pnl.report_for(self._campaign_id)
        if report is None:
            return []

        entries = [
            CostEntry(
                category=category,
                amount=_cents_to_decimal(amount_cents),
                trace_id=None,
            )
            for category, amount_cents in report.cost_by_category_cents.items()
        ]
        if report.revenue_cents:
            entries.append(
                CostEntry(
                    category="meeting_booked",
                    amount=_cents_to_decimal(report.revenue_cents),
                    trace_id=None,
                )
            )
        return entries


def _cents_to_decimal(cents: int) -> Decimal:
    return (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"))
