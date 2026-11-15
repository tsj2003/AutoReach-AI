from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from engine.core.types import Engagement, Prospect


def _client(tmp_path, monkeypatch):
    from cockpit import create_app

    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    return TestClient(create_app(db_url=f"sqlite:///{tmp_path / 'webhook.db'}"))


def _booking_body() -> bytes:
    return json.dumps({
        "triggerEvent": "BOOKING_CREATED",
        "payload": {
            "uid": "booking-123",
            "title": "Intro",
            "startTime": "2026-06-01T15:00:00Z",
            "attendees": [{"email": "prospect@example.com", "name": "Prospect"}],
        },
    }).encode("utf-8")


def _scoped_booking_body(*, tenant_id: str, engagement_id: str, email: str = "prospect@example.com") -> bytes:
    return json.dumps({
        "triggerEvent": "BOOKING_CREATED",
        "payload": {
            "uid": "booking-123",
            "title": "Intro",
            "startTime": "2026-06-01T15:00:00Z",
            "attendees": [{"email": email, "name": "Prospect"}],
            "metadata": {
                "tenant_id": tenant_id,
                "engagement_id": engagement_id,
            },
        },
    }).encode("utf-8")


def _signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_calcom_webhook_requires_secret_in_production(tmp_path, monkeypatch):
    monkeypatch.delenv("CALCOM_WEBHOOK_SECRET", raising=False)
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/webhooks/calcom/booking",
        content=_booking_body(),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 503
    assert "CALCOM_WEBHOOK_SECRET" in response.text


def test_calcom_webhook_rejects_bad_signature_in_production(tmp_path, monkeypatch):
    monkeypatch.setenv("CALCOM_WEBHOOK_SECRET", "cal-secret")
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/webhooks/calcom/booking",
        content=_booking_body(),
        headers={
            "Content-Type": "application/json",
            "X-Cal-Signature-256": "sha256=bad",
        },
    )

    assert response.status_code == 401


def test_calcom_webhook_accepts_signed_payload_in_production(tmp_path, monkeypatch):
    secret = "cal-secret"
    body = _booking_body()
    signature = _signature(secret, body)
    monkeypatch.setenv("CALCOM_WEBHOOK_SECRET", secret)
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/webhooks/calcom/booking",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Cal-Signature-256": f"sha256={signature}",
        },
    )

    assert response.status_code == 200
    assert response.json()["matched"] is False


def test_calcom_webhook_books_only_scoped_tenant_campaign(tmp_path, monkeypatch):
    secret = "cal-secret"
    monkeypatch.setenv("CALCOM_WEBHOOK_SECRET", secret)
    client = _client(tmp_path, monkeypatch)
    store = client.app.state.store

    store.save_engagement(
        Engagement(id="eng-alpha", customer_name="Alpha", offer="O", icp_description="I"),
        tenant_id="t-alpha",
    )
    store.save_engagement(
        Engagement(id="eng-beta", customer_name="Beta", offer="O", icp_description="I"),
        tenant_id="t-beta",
    )
    store.save_prospect(
        Prospect(id="p-alpha", engagement_id="eng-alpha", email="prospect@example.com"),
        tenant_id="t-alpha",
    )
    store.save_prospect(
        Prospect(id="p-beta", engagement_id="eng-beta", email="prospect@example.com"),
        tenant_id="t-beta",
    )

    body = _scoped_booking_body(tenant_id="t-alpha", engagement_id="eng-alpha")
    response = client.post(
        "/webhooks/calcom/booking",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Cal-Signature-256": f"sha256={_signature(secret, body)}",
        },
    )

    assert response.status_code == 200
    assert response.json()["matched"] is True
    assert store.get_prospect("p-alpha").status == "booked"
    assert store.get_prospect("p-beta").status == "new"
    assert len(list(store.list_meetings("eng-alpha"))) == 1
    assert len(list(store.list_meetings("eng-beta"))) == 0


def test_calcom_scoped_webhook_books_api_created_contact(tmp_path, monkeypatch):
    secret = "cal-secret"
    monkeypatch.setenv("CALCOM_WEBHOOK_SECRET", secret)
    client = _client(tmp_path, monkeypatch)
    store = client.app.state.store

    store.save_engagement(
        Engagement(id="eng-alpha", customer_name="Alpha", offer="O", icp_description="I"),
        tenant_id="t-alpha",
    )
    prospect = client.app.state.ops.add_prospect(
        engagement_id="eng-alpha",
        email="api-created@example.com",
    )

    body = _scoped_booking_body(
        tenant_id="t-alpha",
        engagement_id="eng-alpha",
        email="api-created@example.com",
    )
    response = client.post(
        "/webhooks/calcom/booking",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Cal-Signature-256": f"sha256={_signature(secret, body)}",
        },
    )

    assert response.status_code == 200
    assert response.json()["matched"] is True
    assert store.get_prospect(prospect.id).status == "booked"


def test_calcom_webhook_refuses_unscoped_production_match(tmp_path, monkeypatch):
    secret = "cal-secret"
    monkeypatch.setenv("CALCOM_WEBHOOK_SECRET", secret)
    client = _client(tmp_path, monkeypatch)
    store = client.app.state.store

    store.save_engagement(
        Engagement(id="eng-alpha", customer_name="Alpha", offer="O", icp_description="I"),
        tenant_id="t-alpha",
    )
    store.save_prospect(
        Prospect(id="p-alpha", engagement_id="eng-alpha", email="prospect@example.com"),
        tenant_id="t-alpha",
    )

    body = _booking_body()
    response = client.post(
        "/webhooks/calcom/booking",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Cal-Signature-256": f"sha256={_signature(secret, body)}",
        },
    )

    assert response.status_code == 200
    assert response.json()["matched"] is False
    assert "scope" in response.json()["message"]
    assert store.get_prospect("p-alpha").status == "new"
    assert len(list(store.list_meetings("eng-alpha"))) == 0
