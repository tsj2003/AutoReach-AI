"""Official LinkedIn Sign-In (OIDC) connect path."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from cockpit import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    monkeypatch.delenv("LINKEDIN_CLIENT_ID", raising=False)
    monkeypatch.delenv("LINKEDIN_CLIENT_SECRET", raising=False)
    app = create_app(db_url=f"sqlite:///{tmp_path / 'li_oauth.db'}")
    return TestClient(app)


def _auth(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/auth/signup",
        json={"email": "li-oauth@attainly.test", "password": "Password123!", "company_name": "Attainly"},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_oauth_start_requires_config(client: TestClient):
    headers = _auth(client)
    res = client.post(
        "/api/linkedin/oauth/start",
        json={"redirect_uri": "http://testserver/api/linkedin/oauth/callback"},
        headers=headers,
    )
    assert res.status_code == 503
    assert "LINKEDIN_CLIENT_ID" in res.json()["detail"]


def test_oauth_start_and_callback(client: TestClient, monkeypatch):
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "li-client-test")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "li-secret-test")
    headers = _auth(client)

    started = client.post(
        "/api/linkedin/oauth/start",
        json={"redirect_uri": "http://testserver/api/linkedin/oauth/callback"},
        headers=headers,
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert "linkedin.com/oauth/v2/authorization" in body["authorization_url"]
    assert "li-client-test" in body["authorization_url"]
    state = body["state"]

    tokens = {
        "access_token": "li-access-token",
        "expires_in": 3600,
        "scope": "openid profile email",
        "token_type": "Bearer",
    }
    userinfo = {
        "sub": "AbCdEf",
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "given_name": "Ada",
        "family_name": "Lovelace",
    }
    with patch("cockpit.api.linkedin.exchange_code_for_tokens", return_value=tokens), patch(
        "cockpit.api.linkedin.fetch_userinfo", return_value=userinfo
    ):
        cb = client.get(
            "/api/linkedin/oauth/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
    assert cb.status_code in (302, 307)
    assert "linkedin=connected" in cb.headers.get("location", "")

    seats = client.get("/api/linkedin/seats", headers=headers)
    assert seats.status_code == 200, seats.text
    data = seats.json()
    assert data["count"] >= 1
    seat = data["seats"][0]
    assert seat["auth_method"] == "linkedin_oauth"
    assert seat["can_auto_message"] is False
    assert seat["account_name"] == "Ada Lovelace"
    assert seat["email"] == "ada@example.com"
    assert data["oauth_configured"] is True


def test_oauth_identity_does_not_enable_voyager_automation(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "li-client-test")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "li-secret-test")
    app = create_app(db_url=f"sqlite:///{tmp_path / 'li_oauth2.db'}")
    client = TestClient(app)
    headers = _auth(client)

    started = client.post(
        "/api/linkedin/oauth/start",
        json={"redirect_uri": "http://testserver/api/linkedin/oauth/callback"},
        headers=headers,
    )
    state = started.json()["state"]
    with patch("cockpit.api.linkedin.exchange_code_for_tokens", return_value={"access_token": "t", "expires_in": 60}), patch(
        "cockpit.api.linkedin.fetch_userinfo",
        return_value={"sub": "x1", "name": "Test User", "email": "t@example.com"},
    ):
        client.get("/api/linkedin/oauth/callback", params={"code": "c", "state": state}, follow_redirects=False)

    from engine.dispatch.linkedin import tenant_has_linkedin_seat

    store = app.state.store
    # tenant_id from JWT — pull via seats list
    seats = client.get("/api/linkedin/seats", headers=headers).json()["seats"]
    tid = seats[0]["tenant_id"]
    assert tenant_has_linkedin_seat(store, tid) is False
