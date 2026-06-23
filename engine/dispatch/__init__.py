"""Dispatch-layer mailbox routing and provider abstractions."""

from engine.dispatch.linkedin import LinkedInProvider
from engine.dispatch.adapter import SmartRoutedEmailAdapter
from engine.dispatch.provider import SMTPProvider
from engine.dispatch.router import SmartInboxRouter

__all__ = ["LinkedInProvider", "SmartRoutedEmailAdapter", "SMTPProvider", "SmartInboxRouter"]
