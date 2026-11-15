"""Cross-tenant isolation attack tests — REST API."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from cockpit import create_app
from engine.signals.webhook_client import webhook_request_headers


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOREACH_SIGNALS_ENABLED", "1")
    return TestClient(create_app(db_url=f"sqlite:///{tmp_path / 'iso.db'}"))


def _tenant(client: TestClient, prefix: str) -> tuple[str, dict]:
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@iso.test"
    signup = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "secret123", "company_name": prefix},
    )
    assert signup.status_code == 200, signup.text
    token = signup.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


def test_tenant_b_cannot_access_tenant_a_campaign(api):
    _, headers_a = _tenant(api, "a")
    _, headers_b = _tenant(api, "b")

    camp = api.post(
        "/api/campaigns",
        headers=headers_a,
        json={
            "customer_name": "A Co", "offer": "O", "icp_description": "I",
            "client_cure": "C", "signal_matrix": {"allowed_signal_types": ["funding_round"], "min_signal_stack": 1},
        },
    )
    campaign_id = camp.json()["id"]

    assert api.get(f"/api/campaigns/{campaign_id}", headers=headers_b).status_code in (403, 404)
    assert api.patch(f"/api/campaigns/{campaign_id}", headers=headers_b, json={"customer_name": "Hacked"}).status_code in (403, 404)


def test_tenant_b_cannot_access_tenant_a_webhook_source(api):
    _, headers_a = _tenant(api, "wha")
    _, headers_b = _tenant(api, "whb")

    wh = api.post("/api/signals/sources", headers=headers_a, json={"connector_kind": "webhook", "name": "WH"})
    source_id = wh.json()["source_id"]

    assert api.get(f"/api/signals/sources/{source_id}/health", headers=headers_b).status_code == 404
    assert api.post(f"/api/signals/sources/{source_id}/sync", headers=headers_b).status_code == 404


def test_tenant_b_webhook_to_tenant_a_source_fails_without_secret(api):
    _, headers_a = _tenant(api, "whc")

    wh = api.post("/api/signals/sources", headers=headers_a, json={"connector_kind": "webhook", "name": "WH"})
    source_id = wh.json()["source_id"]
    secret = wh.json()["webhook_secret"]

    payload = {"signal_type": "funding_round", "company_domain": "x.com", "evidence": {"summary": "t"}}
    body = json.dumps(payload).encode()
    hdrs = webhook_request_headers(secret, body, idempotency_key="iso-attack-1")

    assert api.post(f"/api/webhooks/signals/{source_id}", content=body, headers=hdrs).status_code == 200

    bad_secret_body = json.dumps({**payload, "company_domain": "y.com"}).encode()
    bad_hdrs = webhook_request_headers("wrong-secret", bad_secret_body, idempotency_key="iso-attack-2")
    assert api.post(f"/api/webhooks/signals/{source_id}", content=bad_secret_body, headers=bad_hdrs).status_code == 401


def test_tenant_b_cannot_list_tenant_a_inbox(api):
    _, headers_a = _tenant(api, "ina")
    _, headers_b = _tenant(api, "inb")

    camp = api.post(
        "/api/campaigns",
        headers=headers_a,
        json={
            "customer_name": "Inbox A", "offer": "O", "icp_description": "I",
            "client_cure": "C", "signal_matrix": {"allowed_signal_types": ["funding_round"], "min_signal_stack": 1},
        },
    )
    campaign_id = camp.json()["id"]
    assert api.get(f"/api/inbox?campaign_id={campaign_id}", headers=headers_b).status_code in (403, 404)
