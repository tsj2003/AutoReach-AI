"""Auth endpoints must throttle brute-force / enumeration attempts."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cockpit.main import app
from cockpit.api import ratelimit
from cockpit.api.ratelimit import SlidingWindowRateLimiter

client = TestClient(app)


def test_login_is_rate_limited_after_burst():
    """After the per-IP window limit, further login attempts get 429 + Retry-After."""
    # Limit is 25 / 300s; 25 allowed then blocked. Wrong creds → 401 until the cap.
    last = None
    for _ in range(25):
        last = client.post("/api/auth/login", json={"email": "nobody@x.co", "password": "wrong-pass-1"})
        assert last.status_code != 429  # not throttled yet
    blocked = client.post("/api/auth/login", json={"email": "nobody@x.co", "password": "wrong-pass-1"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_reset_clears_counters_between_tests():
    """The autouse conftest reset must actually clear state (isolation guarantee)."""
    # This test runs after the burst above; if reset didn't fire, we'd already be
    # near/over the cap. A fresh login should be allowed.
    r = client.post("/api/auth/login", json={"email": "nobody@x.co", "password": "wrong-pass-1"})
    assert r.status_code != 429


def test_sliding_window_unit():
    """Unit-level: the limiter allows N then blocks, with a positive retry_after."""
    lim = SlidingWindowRateLimiter()
    now = 1000.0
    for i in range(3):
        allowed, _ = lim.check("k", limit=3, window_seconds=60, now=now + i)
        assert allowed
    allowed, retry_after = lim.check("k", limit=3, window_seconds=60, now=now + 3)
    assert not allowed
    assert retry_after > 0
    # After the window fully passes, it allows again.
    allowed, _ = lim.check("k", limit=3, window_seconds=60, now=now + 100)
    assert allowed


def test_forwarded_for_is_used_as_client_key():
    """Different X-Forwarded-For clients get independent budgets."""
    ratelimit.reset_rate_limiter()
    headers_a = {"X-Forwarded-For": "203.0.113.1"}
    headers_b = {"X-Forwarded-For": "203.0.113.2"}
    # Exhaust client A.
    for _ in range(25):
        client.post("/api/auth/login", json={"email": "a@x.co", "password": "nope-1"}, headers=headers_a)
    a_blocked = client.post("/api/auth/login", json={"email": "a@x.co", "password": "nope-1"}, headers=headers_a)
    assert a_blocked.status_code == 429
    # Client B is unaffected.
    b_ok = client.post("/api/auth/login", json={"email": "b@x.co", "password": "nope-1"}, headers=headers_b)
    assert b_ok.status_code != 429


def test_prepended_forwarded_for_cannot_bypass(monkeypatch):
    """Anti-spoof: rotating the client-forgeable LEFTMOST XFF token must not bypass.

    A fronting proxy appends the real peer IP; with the default single trusted
    hop the limiter keys on that rightmost entry, so a client rotating leftmost
    tokens stays in one bucket and is still throttled.
    """
    monkeypatch.delenv("AUTOREACH_TRUSTED_PROXY_HOPS", raising=False)  # default 1 = rightmost
    ratelimit.reset_rate_limiter()
    real = "203.0.113.9"  # what the trusted proxy appends
    for i in range(25):
        r = client.post(
            "/api/auth/login",
            json={"email": "a@x.co", "password": "no"},
            headers={"X-Forwarded-For": f"10.0.0.{i}, {real}"},
        )
        assert r.status_code != 429
    blocked = client.post(
        "/api/auth/login",
        json={"email": "a@x.co", "password": "no"},
        headers={"X-Forwarded-For": f"10.0.0.250, {real}"},
    )
    assert blocked.status_code == 429
