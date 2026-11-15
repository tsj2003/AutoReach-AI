"""Plan lead-cap enforcement shared by contact create, CSV, scrape, intent."""

from __future__ import annotations

from fastapi import HTTPException

from engine.policies.plan_limits import get_plan_limits


def count_tenant_leads(store, tenant_id: str) -> int:
    count_fn = getattr(store, "count_prospects_for_tenant", None)
    if callable(count_fn):
        return int(count_fn(tenant_id))
    total = 0
    for eng in store.list_engagements(tenant_id=tenant_id):
        if getattr(eng, "status", "") == "cancelled":
            continue
        total += len(list(store.list_prospects(eng.id, limit=100_000)))
    return total


def assert_under_lead_cap(store, *, tenant_id: str, plan: str, delta: int = 1) -> None:
    """Raise 403 if adding `delta` leads would exceed the plan cap."""
    if delta <= 0:
        return
    limits = get_plan_limits(plan)
    current = count_tenant_leads(store, tenant_id)
    if current + delta > limits.max_leads_total:
        raise HTTPException(
            403,
            f"Plan '{limits.plan}' allows {limits.max_leads_total} leads total "
            f"(currently {current}). Upgrade to add more.",
        )
