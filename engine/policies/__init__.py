"""
Engine policies — guardrails that gate actions.

    SendRateLimiter   M5: per-engagement daily caps + sending windows
    PlanLimits        M5: per-plan tier caps
    EspMatcher        M8: route Gmail→Gmail / Outlook→Outlook
"""

from engine.policies.rate_limiter import RateLimitDecision, SendRateLimiter  # noqa: F401
from engine.policies.plan_limits import PLANS, PlanLimits, get_plan_limits  # noqa: F401
from engine.policies.esp_matcher import EspMatcher  # noqa: F401

__all__ = [
    "SendRateLimiter",
    "RateLimitDecision",
    "PlanLimits",
    "PLANS",
    "get_plan_limits",
    "EspMatcher",
]
