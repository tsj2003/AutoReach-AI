"""Dispatch-layer mailbox routing and provider abstractions."""

from engine.dispatch.linkedin import LinkedInProvider, get_active_linkedin_provider, tenant_has_linkedin_seat
from engine.dispatch.linkedin_adapter import LinkedInVoyagerAdapter, normalize_voyager_step_type
from engine.dispatch.adapter import SmartRoutedEmailAdapter
from engine.dispatch.provider import SMTPProvider
from engine.dispatch.router import SmartInboxRouter

__all__ = [
    "LinkedInProvider",
    "LinkedInVoyagerAdapter",
    "SmartRoutedEmailAdapter",
    "SMTPProvider",
    "SmartInboxRouter",
    "get_active_linkedin_provider",
    "normalize_voyager_step_type",
    "tenant_has_linkedin_seat",
]
