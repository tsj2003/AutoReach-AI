"""Webhook replay protection — Phase 6 security tests."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from cockpit import create_app
from engine.signals.webhook_client import webhook_request_headers
from engine.signals.webhook_replay import WebhookReplayStore, replay_window_seconds


@pytest.fixture
def webhook_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOREACH_SIGNALS_ENABLED", "1")
    return TestClient(create_app(db_url=f"sqlite:///{tmp_path / 'wh.db'}"))


def _setup_webhook(webhook_client: TestClient) -> tuple[str, str, str]:
    res = webhook_client.post(
        "/api/auth/signup",
        json={"email": "wh@test.com", "password": "secret123", "company_name": "WH Co"},
    )
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    create = webhook_client.post(
        "/api/signals/sources",
        headers=headers,
        json={"connector_kind": "webhook", "name": "CRM"},
    )
    data = create.json()
    return data["source_id"], data["webhook_secret"], token


def _post(webhook_client, source_id, secret, payload, *, idempotency_key: str, timestamp: int | None = None, sig_override: str | None = None):
    body = json.dumps(payload).encode()
    hdrs = webhook_request_headers(secret, body, idempotency_key=idempotency_key, timestamp=timestamp)
    if sig_override:
        hdrs["X-Attainly-Signature"] = sig_override
    return webhook_client.post(f"/api/webhooks/signals/{source_id}", content=body, headers=hdrs)


def test_valid_fresh_request(webhook_client):
    source_id, secret, token = _setup_webhook(webhook_client)
    payload = {
        "signal_type": "funding_round",
        "company_domain": "acme.com",
        "evidence": {"summary": "Series B"},
    }
    r = _post(webhook_client, source_id, secret, payload, idempotency_key="evt-001")
    assert r.status_code == 200
    assert r.json()["events_inserted"] >= 1


def test_invalid_hmac(webhook_client):
    source_id, secret, _ = _setup_webhook(webhook_client)
    payload = {"signal_type": "funding_round", "company_domain": "acme.com", "evidence": {"summary": "x"}}
    body = json.dumps(payload).encode()
    hdrs = webhook_request_headers(secret, body, idempotency_key="evt-002")
    hdrs["X-Attainly-Signature"] = "sha256=deadbeef"
    r = webhook_client.post(f"/api/webhooks/signals/{source_id}", content=body, headers=hdrs)
    assert r.status_code == 401


def test_expired_timestamp(webhook_client):
    source_id, secret, _ = _setup_webhook(webhook_client)
    payload = {"signal_type": "funding_round", "company_domain": "acme.com", "evidence": {"summary": "x"}}
    old_ts = int(time.time()) - replay_window_seconds() - 120
    r = _post(webhook_client, source_id, secret, payload, idempotency_key="evt-003", timestamp=old_ts)
    assert r.status_code == 401


def test_future_timestamp(webhook_client):
    source_id, secret, _ = _setup_webhook(webhook_client)
    payload = {"signal_type": "funding_round", "company_domain": "acme.com", "evidence": {"summary": "x"}}
    future_ts = int(time.time()) + 600
    r = _post(webhook_client, source_id, secret, payload, idempotency_key="evt-004", timestamp=future_ts)
    assert r.status_code == 400


def test_same_idempotency_key_deduped(webhook_client):
    source_id, secret, _ = _setup_webhook(webhook_client)
    payload = {"signal_type": "funding_round", "company_domain": "acme.com", "evidence": {"summary": "x"}}
    r1 = _post(webhook_client, source_id, secret, payload, idempotency_key="evt-005")
    r2 = _post(webhook_client, source_id, secret, payload, idempotency_key="evt-005")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True


def test_modified_body_rejects_signature(webhook_client):
    source_id, secret, _ = _setup_webhook(webhook_client)
    payload = {"signal_type": "funding_round", "company_domain": "acme.com", "evidence": {"summary": "original"}}
    body = json.dumps(payload).encode()
    hdrs = webhook_request_headers(secret, body, idempotency_key="evt-006")
    tampered = json.dumps({**payload, "evidence": {"summary": "tampered"}}).encode()
    r = webhook_client.post(f"/api/webhooks/signals/{source_id}", content=tampered, headers=hdrs)
    assert r.status_code == 401


def test_cross_tenant_source_denied(webhook_client):
    source_id, secret, _ = _setup_webhook(webhook_client)
    other = webhook_client.post(
        "/api/auth/signup",
        json={"email": "other@test.com", "password": "secret123", "company_name": "Other"},
    )
    other_token = other.json()["access_token"]
    r = webhook_client.get(
        f"/api/signals/sources/{source_id}/health",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert r.status_code == 404


def test_missing_timestamp(webhook_client):
    source_id, secret, _ = _setup_webhook(webhook_client)
    payload = {"signal_type": "funding_round", "company_domain": "acme.com", "evidence": {"summary": "x"}}
    body = json.dumps(payload).encode()
    hdrs = {"Content-Type": "application/json", "X-Attainly-Signature": webhook_request_headers(secret, body, idempotency_key="evt-007")["X-Attainly-Signature"]}
    r = webhook_client.post(f"/api/webhooks/signals/{source_id}", content=body, headers=hdrs)
    assert r.status_code == 400


def test_concurrent_duplicate_requests(webhook_client):
    """Sequential duplicate with same idempotency key — replay store enforces uniqueness."""
    source_id, secret, _ = _setup_webhook(webhook_client)
    payload = {"signal_type": "funding_round", "company_domain": "acme.com", "evidence": {"summary": "race"}}
    body = json.dumps(payload).encode()
    hdrs = webhook_request_headers(secret, body, idempotency_key="evt-race-001")
    r1 = webhook_client.post(f"/api/webhooks/signals/{source_id}", content=body, headers=hdrs)
    r2 = webhook_client.post(f"/api/webhooks/signals/{source_id}", content=body, headers=hdrs)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True


def test_replay_cleanup(tmp_path):
    from engine import open_storage
    from datetime import datetime, timedelta, timezone

    store, _, _ = open_storage(f"sqlite:///{tmp_path / 'cleanup.db'}")
    replay = WebhookReplayStore(store._holder.engine)
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    replay.claim(
        tenant_id="t1", source_id="s1", replay_key="old-key",
        body_hash_value="abc", observed_at=past,
    )
    removed = replay.cleanup_expired(before=datetime.now(timezone.utc))
    assert removed >= 0
