"""
M1 + M2 — JWT auth + REST API integration tests.

Tests run against a fresh in-memory SQLite DB via the FastAPI TestClient.
No real Gmail, no real Gemini, no network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from cockpit import create_app
    app = create_app(db_url=f"sqlite:///{tmp_path / 'api_test.db'}")
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def auth_client(tmp_path):
    """Client with a pre-registered + logged-in user. Returns (client, tokens_dict)."""
    from cockpit import create_app
    app = create_app(db_url=f"sqlite:///{tmp_path / 'api_auth.db'}")
    client = TestClient(app, raise_server_exceptions=True)

    r = client.post("/api/auth/signup", json={
        "email": "founder@acme.com",
        "password": "Password1!",
        "full_name": "Alice Founder",
        "company_name": "Acme Inc",
    })
    assert r.status_code == 200, r.text
    tokens = r.json()
    return client, tokens


# ─────────────────────────────────────────────────────────────────────────────
# Auth: signup / login / me / refresh
# ─────────────────────────────────────────────────────────────────────────────


def test_signup_creates_tenant_and_returns_jwt(client):
    r = client.post("/api/auth/signup", json={
        "email": "test@example.com",
        "password": "Password1!",
        "full_name": "Test User",
        "company_name": "Test Co",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["email"] == "test@example.com"
    assert body["role"] == "owner"
    # New accounts begin on a 7-day Pro trial.
    assert body["plan"] == "pro"


def test_signup_fails_closed_without_jwt_secret_in_production_like_env(tmp_path, monkeypatch):
    from cockpit import create_app

    from cryptography.fernet import Fernet

    monkeypatch.delenv("AUTOREACH_JWT_SECRET", raising=False)
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db/autoreach")
    # Production also requires the credential encryption key; set it so we reach
    # the JWT check this test is about rather than the encryption boot guard.
    monkeypatch.setenv("AUTOREACH_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    app = create_app(db_url=f"sqlite:///{tmp_path / 'prod_auth_missing_secret.db'}")
    prod_client = TestClient(app, raise_server_exceptions=True)

    r = prod_client.post("/api/auth/signup", json={
        "email": "prod@example.com",
        "password": "Password1!",
        "company_name": "Prod Co",
    })

    assert r.status_code == 503
    assert "JWT signing secret" in r.text


def test_signup_rejects_dev_jwt_secret_in_production_like_env(tmp_path, monkeypatch):
    from cockpit import create_app

    from cryptography.fernet import Fernet

    monkeypatch.setenv("AUTOREACH_JWT_SECRET", "CHANGE_ME_SET_AUTOREACH_JWT_SECRET_IN_ENV")
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db/autoreach")
    monkeypatch.setenv("AUTOREACH_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    app = create_app(db_url=f"sqlite:///{tmp_path / 'prod_auth_dev_secret.db'}")
    prod_client = TestClient(app, raise_server_exceptions=True)

    r = prod_client.post("/api/auth/signup", json={
        "email": "prod-dev@example.com",
        "password": "Password1!",
        "company_name": "Prod Co",
    })

    assert r.status_code == 503
    assert "JWT signing secret" in r.text


def test_signup_duplicate_email_returns_409(client):
    payload = {"email": "dup@example.com", "password": "Password1!"}
    client.post("/api/auth/signup", json=payload)
    r = client.post("/api/auth/signup", json=payload)
    assert r.status_code == 409


def test_signup_weak_password_rejected(client):
    r = client.post("/api/auth/signup", json={
        "email": "x@y.com", "password": "short",
    })
    assert r.status_code == 422


def test_signup_invalid_email_rejected(client):
    r = client.post("/api/auth/signup", json={
        "email": "not-an-email", "password": "Password1!",
    })
    assert r.status_code == 422


def test_login_valid_returns_tokens(auth_client):
    client, _ = auth_client
    r = client.post("/api/auth/login", json={
        "email": "founder@acme.com", "password": "Password1!",
    })
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_wrong_password_returns_401(auth_client):
    client, _ = auth_client
    r = client.post("/api/auth/login", json={
        "email": "founder@acme.com", "password": "WrongPass1!",
    })
    assert r.status_code == 401


def test_me_returns_user_info(auth_client):
    client, tokens = auth_client
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "founder@acme.com"
    assert body["role"] == "owner"
    assert body["tenant_name"] == "Acme Inc"


def test_me_without_token_returns_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_refresh_returns_new_access_token(auth_client):
    import time
    client, tokens = auth_client
    time.sleep(1)  # ensure exp differs by at least 1 second
    r = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    assert new_token  # not empty
    # The iat claim will differ — decode both and compare
    import jwt as _jwt
    orig = _jwt.decode(tokens["access_token"], options={"verify_signature": False})
    new = _jwt.decode(new_token, options={"verify_signature": False})
    assert new["exp"] > orig["exp"] - 5  # new exp is close to or after old exp


def test_refresh_with_access_token_rejected(auth_client):
    client, tokens = auth_client
    r = client.post("/api/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Tenant isolation
# ─────────────────────────────────────────────────────────────────────────────


def test_tenant_isolation(tmp_path):
    """User A cannot see User B's campaigns."""
    from cockpit import create_app
    app = create_app(db_url=f"sqlite:///{tmp_path / 'iso.db'}")
    c = TestClient(app, raise_server_exceptions=True)

    # Sign up two tenants.
    r_a = c.post("/api/auth/signup", json={"email": "a@a.com", "password": "Password1!", "company_name": "TenantA"})
    r_b = c.post("/api/auth/signup", json={"email": "b@b.com", "password": "Password1!", "company_name": "TenantB"})
    token_a = r_a.json()["access_token"]
    token_b = r_b.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # A creates a campaign.
    r = c.post("/api/campaigns", json={
        "customer_name": "A's Campaign", "offer": "O", "icp_description": "I",
    }, headers=headers_a)
    assert r.status_code == 201
    campaign_id = r.json()["id"]

    # B cannot see A's campaign in the list.
    r_list = c.get("/api/campaigns", headers=headers_b)
    assert r_list.status_code == 200
    assert not any(c2["id"] == campaign_id for c2 in r_list.json())

    # B cannot access A's campaign by ID.
    r_get = c.get(f"/api/campaigns/{campaign_id}", headers=headers_b)
    assert r_get.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Campaigns CRUD (M2)
# ─────────────────────────────────────────────────────────────────────────────


def test_campaign_create_list_get(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Create
    r = client.post("/api/campaigns", json={
        "customer_name": "Prospect Co", "offer": "AI outbound",
        "icp_description": "B2B SaaS founders",
        "monthly_meeting_target": 20,
        "price_per_outcome_cents": 50000,
        "hitl_threshold": 5,
    }, headers=h)
    assert r.status_code == 201
    cid = r.json()["id"]
    assert r.json()["customer_name"] == "Prospect Co"

    # List
    r = client.get("/api/campaigns", headers=h)
    assert r.status_code == 200
    assert any(c2["id"] == cid for c2 in r.json())

    # Get
    r = client.get(f"/api/campaigns/{cid}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == cid
    assert body["agents"]          # default agent created
    assert "pnl" in body
    assert "events" in body


def test_campaign_create_persists_client_cure_and_signal_matrix(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}

    r = client.post("/api/campaigns", json={
        "customer_name": "Intent Co",
        "offer": "O",
        "icp_description": "I",
        "client_cure": "Fixes outbound teams missing fresh funding triggers.",
        "allowed_signal_types": ["funding_round", "job_posting", "funding_round"],
        "monthly_budget_cents": 100000,
    }, headers=h)

    assert r.status_code == 201
    created = r.json()
    assert created["client_cure"] == "Fixes outbound teams missing fresh funding triggers."
    assert created["allowed_signal_types"] == ["funding_round", "job_posting"]

    fetched = client.get(f"/api/campaigns/{created['id']}", headers=h).json()
    assert fetched["signal_matrix"]["allowed_signal_types"] == ["funding_round", "job_posting"]

    patched = client.patch(
        f"/api/campaigns/{created['id']}",
        json={"allowed_signal_types": ["tech_stack_change"]},
        headers=h,
    ).json()
    assert patched["allowed_signal_types"] == ["tech_stack_change"]


def test_campaign_patch(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/api/campaigns", json={"customer_name": "Old Name", "offer": "O", "icp_description": "I"}, headers=h)
    cid = r.json()["id"]
    r = client.patch(f"/api/campaigns/{cid}", json={"customer_name": "New Name"}, headers=h)
    assert r.status_code == 200
    assert r.json()["customer_name"] == "New Name"


def test_campaign_delete_soft(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/api/campaigns", json={"customer_name": "Delete Me", "offer": "O", "icp_description": "I"}, headers=h)
    cid = r.json()["id"]
    r = client.delete(f"/api/campaigns/{cid}", headers=h)
    assert r.status_code == 204
    r = client.get(f"/api/campaigns/{cid}", headers=h)
    assert r.json()["status"] == "cancelled"


# ─────────────────────────────────────────────────────────────────────────────
# Contacts (M2 + M10 cursor pagination)
# ─────────────────────────────────────────────────────────────────────────────


def test_contacts_create_and_list(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/api/campaigns", json={"customer_name": "C", "offer": "O", "icp_description": "I"}, headers=h)
    cid = r.json()["id"]

    # Add via CSV upload
    csv_bytes = b"email,name,company\nalice@a.com,Alice,Acme\nbob@b.com,Bob,Beta\n"
    r = client.post("/api/contacts/upload", params={"campaign_id": cid},
                    files={"file": ("p.csv", csv_bytes, "text/csv")}, headers=h)
    assert r.status_code == 200
    assert r.json()["loaded"] == 2

    # List first page
    r = client.get("/api/contacts", params={"campaign_id": cid, "limit": 1}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    assert body["has_more"] is True
    cursor = body["next_cursor"]

    # Second page
    r = client.get("/api/contacts", params={"campaign_id": cid, "limit": 1, "cursor": cursor}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    assert body["has_more"] is False


def test_contacts_upload_invalid_csv(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/api/campaigns", json={"customer_name": "C", "offer": "O", "icp_description": "I"}, headers=h)
    cid = r.json()["id"]
    # CSV without email column
    bad_csv = b"name,company\nAlice,Acme\n"
    r = client.post("/api/contacts/upload", params={"campaign_id": cid},
                    files={"file": ("p.csv", bad_csv, "text/csv")}, headers=h)
    assert r.status_code == 200
    assert r.json()["loaded"] == 0
    assert r.json()["errors"]


# ─────────────────────────────────────────────────────────────────────────────
# Inbox / Replies (M2)
# ─────────────────────────────────────────────────────────────────────────────


def test_inbox_list_and_discard(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Create campaign + prospect + reply
    r = client.post("/api/campaigns", json={"customer_name": "C", "offer": "O", "icp_description": "I"}, headers=h)
    cid = r.json()["id"]
    app = client.app
    ops = app.state.ops
    p = ops.add_prospect(engagement_id=cid, email="x@y.com")
    reply = ops.record_reply(engagement_id=cid, prospect_id=p.id, snippet="hi, interested")

    r = client.get("/api/inbox", params={"campaign_id": cid}, headers=h)
    assert r.status_code == 200
    replies = r.json()
    assert len(replies) == 1
    assert replies[0]["classification"] == "objection"

    r = client.post(f"/api/inbox/{reply.id}/discard", headers=h)
    assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Meetings (M2)
# ─────────────────────────────────────────────────────────────────────────────


def test_meetings_create_and_qualify(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}

    r = client.post("/api/campaigns", json={
        "customer_name": "C", "offer": "O", "icp_description": "I",
        "price_per_outcome_cents": 50000,
    }, headers=h)
    cid = r.json()["id"]
    app = client.app
    p = app.state.ops.add_prospect(engagement_id=cid, email="z@z.com")

    r = client.post("/api/meetings", json={
        "campaign_id": cid, "prospect_id": p.id,
        "scheduled_for": "2026-06-01T15:00:00+00:00",
    }, headers=h)
    assert r.status_code == 201
    mid = r.json()["id"]

    r = client.post(f"/api/meetings/{mid}/status", json={"status": "qualified"}, headers=h)
    assert r.status_code == 200

    r = client.get("/api/meetings", params={"campaign_id": cid, "status": "qualified"}, headers=h)
    assert len(r.json()) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Analytics (M2)
# ─────────────────────────────────────────────────────────────────────────────


def test_analytics_dashboard(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    client.post("/api/campaigns", json={"customer_name": "C", "offer": "O", "icp_description": "I"}, headers=h)
    r = client.get("/api/analytics/dashboard", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "totals" in body
    assert body["totals"]["campaigns"] >= 1
