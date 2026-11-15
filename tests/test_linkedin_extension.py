"""Chrome-extension zip, pairing token, and connect-by-token."""

from __future__ import annotations

import io
import zipfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from cockpit import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    app = create_app(db_url=f"sqlite:///{tmp_path / 'li_ext.db'}")
    return TestClient(app)


def _auth(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/auth/signup",
        json={"email": "founder@attainly.test", "password": "Password123!", "company_name": "Attainly"},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_chrome_extension_zip_unauthenticated(client: TestClient):
    res = client.get("/api/linkedin/chrome-extension.zip")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/zip")
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = zf.namelist()
    assert "attainly-linkedin-helper/manifest.json" in names
    assert "attainly-linkedin-helper/background.js" in names
    assert "attainly-linkedin-helper/popup.html" in names
    manifest = zf.read("attainly-linkedin-helper/manifest.json").decode("utf-8")
    assert '"manifest_version": 3' in manifest
    assert "cookies" in manifest


def test_pairing_token_requires_auth(client: TestClient):
    assert client.get("/api/linkedin/pairing-token").status_code == 401
    assert client.post("/api/linkedin/pairing-token").status_code == 401


def test_pairing_and_connect_by_token(client: TestClient):
    headers = _auth(client)
    minted = client.post("/api/linkedin/pairing-token", headers=headers)
    assert minted.status_code == 200, minted.text
    token = minted.json()["token"]
    assert token.startswith("ATN-")

    fake_session = {
        "ok": True,
        "authenticated": True,
        "mode": "live_voyager",
        "public_id": "jane-doe",
        "full_name": "Jane Doe",
        "member_urn": "urn:li:fsd_profile:ACoAAJane",
        "headline": "CRO",
    }
    with patch("cockpit.api.linkedin.LinkedInProvider.validate_session_sync", return_value=fake_session):
        connected = client.post(
            "/api/linkedin/connect-by-token",
            json={"token": token, "li_at": "AQEDAR_fake_cookie_value", "jsession_id": '"ajax:123"'},
        )
    assert connected.status_code == 200, connected.text
    body = connected.json()
    assert body["ok"] is True
    assert body["seat"]["account_name"] == "Jane Doe"
    assert body["has_encrypted_cookie"] is True

    reused = client.post(
        "/api/linkedin/connect-by-token",
        json={"token": token, "li_at": "AQEDAR_fake_cookie_value"},
    )
    assert reused.status_code in (401, 409)

    seats = client.get("/api/linkedin/seats", headers=headers)
    assert seats.status_code == 200
    assert seats.json()["count"] >= 1
