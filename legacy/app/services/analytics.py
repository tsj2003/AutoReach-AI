"""
PostHog product analytics wrapper for AutoReach-AI.
Tracks user actions for product insights without PII exposure.
"""

import os
import logging

logger = logging.getLogger(__name__)

_client_initialized = False


def _ensure_init():
    """Lazy-initialize PostHog client."""
    global _client_initialized
    if _client_initialized:
        return True
    api_key = os.getenv("POSTHOG_API_KEY")
    if not api_key:
        return False
    try:
        import posthog
        posthog.api_key = api_key
        posthog.host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
        _client_initialized = True
        return True
    except ImportError:
        logger.debug("posthog package not installed, analytics disabled")
        return False


def track(user_id, event, properties=None):
    """Track a user event in PostHog."""
    if not _ensure_init():
        return
    try:
        import posthog
        posthog.capture(str(user_id), event, properties or {})
    except Exception as e:
        logger.debug(f"PostHog track failed: {e}")


def identify(user_id, traits=None):
    """Identify a user with traits in PostHog."""
    if not _ensure_init():
        return
    try:
        import posthog
        posthog.identify(str(user_id), traits or {})
    except Exception as e:
        logger.debug(f"PostHog identify failed: {e}")
