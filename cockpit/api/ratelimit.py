"""Lightweight rate limiting for sensitive endpoints.

A per-(bucket, client-IP) sliding-window limiter that throttles brute-force and
enumeration attempts on the auth endpoints. It has no external dependency.

CLIENT IP: derived from a TRUSTED proxy hop, never the raw leftmost
X-Forwarded-For token. A fronting proxy (DigitalOcean App Platform ingress)
APPENDS the real peer IP, so the leftmost entries are client-forgeable but the
rightmost `AUTOREACH_TRUSTED_PROXY_HOPS` (default 1) entry is not. Keying on the
attacker-controlled leftmost token would let anyone bypass the limit (fresh
value per request) or lock out a victim (forge their IP); keying on the trusted
hop prevents both. Set AUTOREACH_TRUSTED_PROXY_HOPS to match your actual proxy
depth — too low over-shares buckets (false 429s for co-located users), too high
re-opens spoofing.

SCOPE / HONESTY: state is in-process. Counters are therefore PER WORKER, and the
web tier runs gunicorn with --workers 2, so the effective per-IP budget before a
429 is roughly `limit x worker_count` (~2x today). It also does not span
multiple instances. This is a best-effort first-line guard, not a complete
account-takeover defense — pair it with the existing strong password hashing
and, for exact/shared limits, move to the available Redis/Valkey (REDIS_URL)
backend or pin the web process to a single worker.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request

# The limiter keys on client IP; bound memory so a flood of distinct keys can't
# OOM the process. Sweep idle keys at most once per interval (never on the hot
# path per-request), and hard-reset if a flood blows past the hard cap.
_SOFT_KEY_CAP = 20_000
_HARD_KEY_CAP = 100_000
_MAX_IDLE_SECONDS = 3_600.0  # >= the largest window we enforce
_EVICT_INTERVAL_SECONDS = 60.0


class SlidingWindowRateLimiter:
    """Thread-safe in-process sliding-window counter with bounded memory."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._last_evict = 0.0

    def check(self, key: str, *, limit: int, window_seconds: float, now: float | None = None) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds).

        Records the hit when allowed. When blocked, retry_after is the time until
        the oldest in-window hit ages out.
        """
        now = time.monotonic() if now is None else now
        cutoff = now - window_seconds
        with self._lock:
            self._maybe_evict_locked(now)
            hits = [t for t in self._hits[key] if t >= cutoff]
            if len(hits) >= limit:
                self._hits[key] = hits
                retry_after = hits[0] + window_seconds - now
                return False, max(0.0, retry_after)
            hits.append(now)
            self._hits[key] = hits
            return True, 0.0

    def _maybe_evict_locked(self, now: float) -> None:
        """Bound memory against key-space flooding. Caller holds the lock.

        Time-gated so the O(n) sweep runs at most once per interval, never on
        every request (which would let an attacker turn eviction into a
        lock-contention DoS).
        """
        if len(self._hits) <= _SOFT_KEY_CAP:
            return
        if now - self._last_evict < _EVICT_INTERVAL_SECONDS:
            return
        self._last_evict = now
        idle_cutoff = now - _MAX_IDLE_SECONDS
        for k in [k for k, v in self._hits.items() if not v or v[-1] < idle_cutoff]:
            del self._hits[k]
        if len(self._hits) > _HARD_KEY_CAP:
            # Active flood of unique keys — drop everything rather than OOM.
            self._hits.clear()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._last_evict = 0.0


# Module-level singleton shared across all rate_limit dependencies.
_LIMITER = SlidingWindowRateLimiter()


def reset_rate_limiter() -> None:
    """Clear all counters. Used by tests to keep cases isolated."""
    _LIMITER.reset()


def _trusted_proxy_hops() -> int:
    try:
        return max(1, int(os.getenv("AUTOREACH_TRUSTED_PROXY_HOPS", "1")))
    except (TypeError, ValueError):
        return 1


def _client_ip(request: Request) -> str:
    """Return the client IP as seen by the trusted proxy hop.

    Takes the entry `hops` positions from the RIGHT of X-Forwarded-For — the
    address the closest trusted proxy observed — so client-prepended values
    can't create new buckets or impersonate another IP. Falls back to the raw
    peer when there is no forwarding header (e.g. local/direct connections).
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            idx = max(0, len(parts) - _trusted_proxy_hops())
            return parts[idx]
    client = request.client
    return client.host if client else "unknown"


def rate_limit(bucket: str, *, limit: int, window_seconds: float):
    """Build a FastAPI dependency enforcing `limit` requests per window per IP.

    Usage:
        @router.post("/login", dependencies=[Depends(rate_limit("auth-login", limit=25, window_seconds=300))])
    """

    def _dependency(request: Request) -> None:
        key = f"{bucket}:{_client_ip(request)}"
        allowed, retry_after = _LIMITER.check(key, limit=limit, window_seconds=window_seconds)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

    return _dependency
