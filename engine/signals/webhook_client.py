"""Webhook signing helpers for clients and tests."""

from __future__ import annotations

import time

from engine.signals.webhook_auth import sign_payload


def webhook_request_headers(
    secret: str,
    body: bytes,
    *,
    idempotency_key: str,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Build signed webhook headers. HMAC is over raw body bytes."""
    ts = timestamp if timestamp is not None else int(time.time())
    headers = {
        "Content-Type": "application/json",
        "X-Attainly-Signature": sign_payload(secret, body),
        "X-Attainly-Timestamp": str(ts),
        "X-Attainly-Idempotency-Key": idempotency_key,
    }
    if nonce:
        headers["X-Attainly-Nonce"] = nonce
    return headers
