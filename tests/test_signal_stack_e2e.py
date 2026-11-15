"""Signal Stack END-TO-END through the API — the founder demo path (steps 3-4).

Create a campaign with min_signal_stack=2, simulate signals, and confirm the
real ingestor + SignalStackPolicy gate account creation and attach evidence.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cockpit import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(db_url=f"sqlite:///{tmp_path / 'e2e.db'}")
    return TestClient(app, raise_server_exceptions=True)


def _signup(client, email):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "Password1!", "company_name": "Stack Co",
    })
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _campaign(client, headers, *, min_stack):
    r = client.post("/api/campaigns", json={
        "customer_name": "Acme", "offer": "We help teams book meetings safely",
        "icp_description": "Founders", "allowed_signal_types": ["funding_round", "hiring_surge"],
        "min_signal_stack": min_stack,
    }, headers=headers)
    assert r.status_code in (200, 201), r.text
    assert r.json()["min_signal_stack"] == min_stack
    return r.json()["id"]


def test_min_signal_stack_gates_and_evidence_is_attached(client):
    h = _signup(client, "stack-e2e@x.co")
    cid = _campaign(client, h, min_stack=2)

    # One signal on an account → below the stack threshold → no prospect.
    r1 = client.post(f"/api/campaigns/{cid}/signals/simulate", json={"signals": [
        {"signal_type": "funding_round", "company_domain": "hot.com", "payload": {"company": "Hot Co"}},
    ]}, headers=h)
    assert r1.status_code == 200, r1.text
    assert r1.json()["created_count"] == 0

    # Two DISTINCT fresh signals on the same account → one prospect with evidence.
    r2 = client.post(f"/api/campaigns/{cid}/signals/simulate", json={"signals": [
        {"signal_type": "funding_round", "company_domain": "hot.com",
         "payload": {"company": "Hot Co", "contact_email": "ceo@hot.com"}},
        {"signal_type": "hiring_surge", "company_domain": "hot.com", "payload": {"company": "Hot Co"}},
    ]}, headers=h)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["created_count"] == 1
    p = body["prospects"][0]
    assert p["company"] == "Hot Co"
    assert p["email"] == "ceo@hot.com"
    assert p["signal_stack"]["depth"] == 2
    assert {e["signal_type"] for e in p["signal_stack"]["evidence"]} == {"funding_round", "hiring_surge"}
    assert body["openinference_trace_id"]  # trace id surfaced (demo step 10)


def test_simulate_is_tenant_scoped(client):
    owner = _signup(client, "owner-e2e@x.co")
    cid = _campaign(client, owner, min_stack=1)
    intruder = _signup(client, "intruder-e2e@x.co")
    r = client.post(f"/api/campaigns/{cid}/signals/simulate", json={"signals": [
        {"signal_type": "funding_round", "company_domain": "x.com"},
    ]}, headers=intruder)
    assert r.status_code == 404  # cannot touch another tenant's campaign


def test_simulate_requires_auth(client):
    r = client.post("/api/campaigns/anything/signals/simulate", json={"signals": []})
    assert r.status_code == 401
