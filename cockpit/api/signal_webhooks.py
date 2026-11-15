"""Signed webhook ingress for tenant signal connectors with replay protection."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from cockpit.api.deps import get_events, get_store
from cockpit.api.ratelimit import rate_limit
from engine.signals.connectors.webhook import WebhookSignalConnector
from engine.signals.feature_flags import is_signals_enabled
from engine.signals.ingestion import SignalIngestionService
from engine.signals.repository import SignalRepository
from engine.signals.service import SignalConnectorService
from engine.signals.webhook_auth import verify_signature_or_raise
from engine.signals.webhook_replay import (
    ReplayCheckResult,
    WebhookReplayError,
    WebhookReplayStore,
    body_hash,
    parse_timestamp_header,
    resolve_nonce,
    resolve_replay_key,
    verify_timestamp_freshness,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/signals", tags=["signal-webhooks"])

_MAX_BODY_BYTES = 2 * 1024 * 1024  # 2MB — matches SSRF fetch cap


def _normalize_headers(request: Request) -> dict[str, str]:
    return {k.lower(): v for k, v in request.headers.items()}


@router.post("/{source_id}", dependencies=[Depends(rate_limit("signal_webhook", limit=120, window_seconds=3600))])
async def receive_signal_webhook(
    source_id: str,
    request: Request,
    store=Depends(get_store),
    events=Depends(get_events),
):
    """Ingest a signed signal event from an external system.

  Headers (required):
    X-Attainly-Signature: sha256=<hmac of raw body>
    X-Attainly-Timestamp: unix epoch seconds

  Headers (recommended):
    X-Attainly-Idempotency-Key: unique per event (or source_event_id in body)
    X-Attainly-Nonce: optional one-time nonce

  HMAC is computed over the **raw request body bytes** — not parsed JSON.
    """
    if not is_signals_enabled():
        raise HTTPException(503, "Signal intelligence disabled")

    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        raise HTTPException(413, "Payload too large")

    headers = _normalize_headers(request)
    repo = SignalRepository(store._holder.engine)

    tenant_id = repo.get_source_tenant_id(source_id)
    if not tenant_id:
        raise HTTPException(404, "Unknown webhook source")

    source = repo.get_source(source_id, tenant_id=tenant_id)
    if not source or not source.get("enabled", True):
        raise HTTPException(404, "Webhook source not found or disabled")

    config = source.get("config") or {}
    secret = str(config.get("webhook_secret") or "")
    sig = headers.get("x-attainly-signature")

    try:
        verify_timestamp_freshness(parse_timestamp_header(headers.get("x-attainly-timestamp")))
        verify_signature_or_raise(secret, body, sig)
    except WebhookReplayError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Invalid JSON body") from exc

    if not isinstance(payload, dict):
        raise HTTPException(400, "Body must be a JSON object")

    try:
        replay_key = resolve_replay_key(headers=headers, payload=payload)
        nonce = resolve_nonce(headers, payload)
    except WebhookReplayError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc

    replay_store = WebhookReplayStore(store._holder.engine)
    claim = replay_store.claim(
        tenant_id=tenant_id,
        source_id=source_id,
        replay_key=replay_key,
        body_hash_value=body_hash(body),
        nonce=nonce,
    )
    if claim is ReplayCheckResult.DUPLICATE:
        return {
            "ok": True,
            "duplicate": True,
            "events_inserted": 0,
            "events_deduplicated": 1,
            "prospects_created": 0,
        }

    connector = WebhookSignalConnector(source_id=source_id, webhook_secret=secret)
    connector.queue_payload(payload)
    ingestion = SignalIngestionService(repository=repo).ingest_connector(
        tenant_id=tenant_id,
        source_id=source_id,
        connector=connector,
        limit=1,
    )

    prospects_created = 0
    if ingestion.events_inserted > 0:
        svc = SignalConnectorService(repository=repo, store=store, events=events)
        sync = svc.sync_source(
            tenant_id=tenant_id,
            source_id=source_id,
            ingest_campaigns=True,
        )
        prospects_created = sync.prospects_created

    return {
        "ok": True,
        "events_inserted": ingestion.events_inserted,
        "events_deduplicated": ingestion.events_deduplicated,
        "prospects_created": prospects_created,
        "trace_id": ingestion.openinference_trace_id,
    }
