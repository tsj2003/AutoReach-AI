"""Shared pytest fixtures for the backend suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the in-process auth rate limiter between tests.

    The limiter keys on client IP, and every TestClient shares the same host, so
    without this reset counters would bleed across tests and trip 429s. Reset is
    a no-op if the module can't be imported (keeps unrelated tests decoupled).
    """
    try:
        from cockpit.api.ratelimit import reset_rate_limiter

        reset_rate_limiter()
    except Exception:
        pass
    yield
