"""
M5 — Plan tier limits.

Defines per-plan caps. Enforced at the API layer (campaign create, mailbox
connect) and surfaced at /api/billing/usage.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimits:
    plan: str
    max_campaigns: int
    max_mailboxes: int
    max_leads_total: int
    max_emails_per_day: int
    personalization: bool


PLANS: dict[str, PlanLimits] = {
    "free": PlanLimits("free", max_campaigns=1, max_mailboxes=1, max_leads_total=500,
                       max_emails_per_day=50, personalization=False),
    "starter": PlanLimits("starter", max_campaigns=5, max_mailboxes=3, max_leads_total=5_000,
                          max_emails_per_day=200, personalization=True),
    "pro": PlanLimits("pro", max_campaigns=25, max_mailboxes=15, max_leads_total=50_000,
                      max_emails_per_day=1_000, personalization=True),
    "enterprise": PlanLimits("enterprise", max_campaigns=10_000, max_mailboxes=1_000,
                             max_leads_total=10_000_000, max_emails_per_day=100_000,
                             personalization=True),
}


def get_plan_limits(plan: str) -> PlanLimits:
    return PLANS.get(plan, PLANS["free"])
