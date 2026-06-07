"""M5 — plan enforcement + billing API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_client(tmp_path):
    import dataclasses
    from cockpit import create_app
    app = create_app(db_url=f"sqlite:///{tmp_path / 'billing.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    r = client.post("/api/auth/signup", json={
        "email": "founder@acme.com", "password": "Password1!", "company_name": "Acme",
    })
    tokens = r.json()
    # New signups get a 7-day Pro trial; these tests exercise the *free* tier,
    # so downgrade the tenant to free (no trial) and re-login for a fresh token.
    store = app.state.store
    tenant = store.get_tenant(tokens["tenant_id"])
    store.save_tenant(dataclasses.replace(tenant, plan="free", trial_ends_at=None))
    relog = client.post("/api/auth/login", json={
        "email": "founder@acme.com", "password": "Password1!",
    }).json()
    return client, relog


def test_billing_plan_endpoint(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.get("/api/billing/plan", headers=h)
    assert r.status_code == 200
    assert r.json()["plan"] == "free"
    assert r.json()["limits"]["max_campaigns"] == 1


def test_billing_usage_endpoint(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    client.post("/api/campaigns", json={"customer_name": "C", "offer": "O", "icp_description": "I"}, headers=h)
    r = client.get("/api/billing/usage", headers=h)
    assert r.status_code == 200
    assert r.json()["usage"]["campaigns"] == 1
    assert r.json()["usage"]["campaigns_limit"] == 1


def test_free_plan_blocks_second_campaign(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r1 = client.post("/api/campaigns", json={"customer_name": "A", "offer": "O", "icp_description": "I"}, headers=h)
    assert r1.status_code == 201
    r2 = client.post("/api/campaigns", json={"customer_name": "B", "offer": "O", "icp_description": "I"}, headers=h)
    assert r2.status_code == 403
    assert "campaign" in r2.json()["detail"].lower()
