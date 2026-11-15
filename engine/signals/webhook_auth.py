"""HMAC verification for tenant webhook signal ingestion.

Signature contract (Attainly webhooks):
- HMAC-SHA256 is computed over the **raw request body bytes** exactly as received.
- Header: ``X-Attainly-Signature: sha256=<hex>``
- Never sign parsed/re-serialized JSON — whitespace and key order matter.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_webhook_secret() -> str:
    return secrets.token_hex(32)


def sign_payload(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, header_value: str | None) -> bool:
    """Verify HMAC on raw body bytes. Returns False if invalid."""
    if not secret or not header_value:
        return False
    expected = sign_payload(secret, body)
    return hmac.compare_digest(expected, header_value.strip())


def verify_signature_or_raise(secret: str, body: bytes, header_value: str | None) -> None:
    from engine.signals.webhook_replay import WebhookReplayError

    if not verify_signature(secret, body, header_value):
        raise WebhookReplayError("invalid_signature", "Invalid webhook signature", 401)
