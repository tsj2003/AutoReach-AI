"""
Social login (Google Identity Services) — endpoint tests.

No real Google network calls: the ID-token verification is monkeypatched so the
test exercises our provisioning + JWT logic, not Google's crypto.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from cockpit import create_app
    app = create_app(db_url=f"sqlite:///{tmp_path / 'social.db'}")
    return TestClient(app, raise_server_exceptions=True)


def test_social_config_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_SIGNIN_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    r = client.get("/api/auth/social-config")
    assert r.status_code == 200
    body = r.json()
    assert body["google_enabled"] is False
    assert body["google_client_id"] == ""


def test_social_config_enabled_when_client_id_set(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_SIGNIN_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    r = client.get("/api/auth/social-config")
    assert r.status_code == 200
    body = r.json()
    assert body["google_enabled"] is True
    assert body["google_client_id"].startswith("test-client-id")


def test_google_login_disabled_returns_503(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_SIGNIN_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    r = client.post("/api/auth/google", json={"credential": "anything"})
    assert r.status_code == 503


def _patch_google_verify(monkeypatch, claims):
    import google.oauth2.id_token as gid

    def fake_verify(credential, request, audience, clock_skew_in_seconds=0):
        assert credential  # token forwarded through
        return claims

    monkeypatch.setattr(gid, "verify_oauth2_token", fake_verify)


def test_google_login_provisions_new_user(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_SIGNIN_CLIENT_ID", "cid.apps.googleusercontent.com")
    _patch_google_verify(monkeypatch, {
        "email": "newperson@gmail.com",
        "email_verified": True,
        "name": "New Person",
    })

    r = client.post("/api/auth/google", json={"credential": "fake-id-token"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "newperson@gmail.com"
    assert body["role"] == "owner"
    assert body["access_token"]

    # The provisioned user can now hit an authenticated route.
    h = {"Authorization": f"Bearer {body['access_token']}"}
    me = client.get("/api/auth/me", headers=h)
    assert me.status_code == 200
    assert me.json()["email"] == "newperson@gmail.com"


def test_google_login_reuses_existing_account(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_SIGNIN_CLIENT_ID", "cid.apps.googleusercontent.com")
    # Pre-create the user via password signup.
    client.post("/api/auth/signup", json={
        "email": "both@acme.com", "password": "Password1!", "company_name": "Acme",
    })
    _patch_google_verify(monkeypatch, {
        "email": "both@acme.com",
        "email_verified": True,
        "name": "Both Ways",
    })

    r = client.post("/api/auth/google", json={"credential": "fake-id-token"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "both@acme.com"


def test_google_login_rejects_unverified_email(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_SIGNIN_CLIENT_ID", "cid.apps.googleusercontent.com")
    _patch_google_verify(monkeypatch, {
        "email": "sketchy@gmail.com",
        "email_verified": False,
        "name": "Sketchy",
    })
    r = client.post("/api/auth/google", json={"credential": "fake-id-token"})
    assert r.status_code == 401


def test_google_login_rejects_invalid_token(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_SIGNIN_CLIENT_ID", "cid.apps.googleusercontent.com")
    import google.oauth2.id_token as gid

    def boom(credential, request, audience, clock_skew_in_seconds=0):
        raise ValueError("Token has wrong audience")

    monkeypatch.setattr(gid, "verify_oauth2_token", boom)
    r = client.post("/api/auth/google", json={"credential": "bad"})
    assert r.status_code == 401
