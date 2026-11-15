"""Persistent webhook replay / idempotency protection."""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from engine.storage.sqlite import signal_webhook_replays_table


class WebhookReplayError(Exception):
    """Base webhook verification error."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ReplayCheckResult(str, Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class WebhookRequestContext:
    """Verified webhook request metadata (after HMAC on raw body)."""

    tenant_id: str
    source_id: str
    replay_key: str
    body_hash: str
    timestamp: datetime
    nonce: str | None


def replay_window_seconds() -> int:
    raw = os.getenv("AUTOREACH_WEBHOOK_REPLAY_WINDOW_SECONDS", "300").strip()
    try:
        return max(60, min(int(raw), 86_400))
    except ValueError:
        return 300


def max_clock_skew_seconds() -> int:
    raw = os.getenv("AUTOREACH_WEBHOOK_MAX_CLOCK_SKEW_SECONDS", "60").strip()
    try:
        return max(0, min(int(raw), 300))
    except ValueError:
        return 60


def body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def parse_timestamp_header(value: str | None) -> datetime:
    if not value or not str(value).strip():
        raise WebhookReplayError("missing_timestamp", "X-Attainly-Timestamp header required", 400)
    raw = str(value).strip()
    try:
        if raw.isdigit():
            ts = int(raw)
        else:
            ts = int(float(raw))
    except ValueError as exc:
        raise WebhookReplayError("invalid_timestamp", "Invalid X-Attainly-Timestamp", 400) from exc
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def verify_timestamp_freshness(ts: datetime, *, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    window = timedelta(seconds=replay_window_seconds())
    skew = timedelta(seconds=max_clock_skew_seconds())
    if ts > now + skew:
        raise WebhookReplayError("future_timestamp", "Webhook timestamp is in the future", 400)
    if ts < now - window:
        raise WebhookReplayError("expired_timestamp", "Webhook timestamp outside replay window", 401)


def resolve_replay_key(
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> str:
    """Idempotency key from header or payload — required for replay protection."""

    for key in ("x-attainly-idempotency-key", "idempotency-key"):
        val = headers.get(key)
        if val and str(val).strip():
            return str(val).strip()[:256]
    for field in ("source_event_id", "event_id", "idempotency_key"):
        val = payload.get(field)
        if val and str(val).strip():
            return str(val).strip()[:256]
    raise WebhookReplayError(
        "missing_idempotency_key",
        "Provide X-Attainly-Idempotency-Key header or source_event_id in payload",
        400,
    )


def resolve_nonce(headers: dict[str, str], payload: dict[str, Any]) -> str | None:
    for key in ("x-attainly-nonce",):
        val = headers.get(key)
        if val and str(val).strip():
            return str(val).strip()[:128]
    val = payload.get("nonce")
    if val and str(val).strip():
        return str(val).strip()[:128]
    return None


class WebhookReplayStore:
    """Durable replay/idempotency state — survives process restarts."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def claim(
        self,
        *,
        tenant_id: str,
        source_id: str,
        replay_key: str,
        body_hash_value: str,
        nonce: str | None = None,
        observed_at: datetime | None = None,
    ) -> ReplayCheckResult:
        """Atomically claim idempotency key. Raises WebhookReplayError on duplicate."""

        now = observed_at or datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=replay_window_seconds() * 2)
        record_id = f"whr_{secrets.token_hex(10)}"
        values = {
            "id": record_id,
            "tenant_id": tenant_id,
            "source_id": source_id,
            "replay_key": replay_key,
            "nonce": nonce,
            "body_hash": body_hash_value,
            "created_at": now,
            "expires_at": expires_at,
        }
        try:
            with self._engine.begin() as conn:
                conn.execute(signal_webhook_replays_table.insert().values(**values))
            return ReplayCheckResult.ACCEPTED
        except IntegrityError:
            return ReplayCheckResult.DUPLICATE

    def cleanup_expired(self, *, before: datetime | None = None) -> int:
        cutoff = before or datetime.now(timezone.utc)
        with self._engine.begin() as conn:
            result = conn.execute(
                delete(signal_webhook_replays_table).where(
                    signal_webhook_replays_table.c.expires_at < cutoff,
                )
            )
        return int(result.rowcount or 0)

    def count_for_source(self, *, tenant_id: str, source_id: str) -> int:
        with self._engine.begin() as conn:
            rows = conn.execute(
                select(signal_webhook_replays_table.c.id).where(
                    signal_webhook_replays_table.c.tenant_id == tenant_id,
                    signal_webhook_replays_table.c.source_id == source_id,
                )
            ).all()
        return len(rows)
