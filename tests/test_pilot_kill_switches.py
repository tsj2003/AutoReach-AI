"""Pilot kill-switch and feature-flag gates."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTOREACH_ENRICHMENT_ENABLED", raising=False)
    monkeypatch.delenv("AUTOREACH_LEARNING_ENABLED", raising=False)
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    from cockpit import create_app

    app = create_app(db_url=f"sqlite:///{tmp_path / 'kill.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    r = client.post(
        "/api/auth/signup",
        json={
            "email": "pilot@example.com",
            "password": "Password1!",
            "full_name": "Pilot",
            "company_name": "Pilot Co",
        },
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def test_campaign_pause_and_resume(auth_client):
    c = auth_client.post(
        "/api/campaigns",
        json={
            "customer_name": "Acme",
            "offer": "Offer",
            "icp_description": "ICP",
            "allowed_signal_types": ["hiring"],
        },
    )
    assert c.status_code == 201, c.text
    cid = c.json()["id"]

    pause = auth_client.post(f"/api/campaigns/{cid}/pause")
    assert pause.status_code == 200
    assert pause.json()["status"] == "paused"
    detail = auth_client.get(f"/api/campaigns/{cid}")
    assert detail.json()["status"] == "paused"

    resume = auth_client.post(f"/api/campaigns/{cid}/resume")
    assert resume.status_code == 200
    assert resume.json()["status"] == "active"


def test_enrichment_disabled_by_default(auth_client, monkeypatch):
    r_default = auth_client.get("/api/enrichment/providers")
    assert r_default.status_code == 200
    monkeypatch.setenv("AUTOREACH_ENRICHMENT_ENABLED", "0")
    r = auth_client.get("/api/enrichment/providers")
    assert r.status_code == 503


def test_learning_disabled_by_default(auth_client, monkeypatch):
    r_default = auth_client.get("/api/learning/weekly")
    assert r_default.status_code == 200
    monkeypatch.setenv("AUTOREACH_LEARNING_ENABLED", "0")
    r = auth_client.get("/api/learning/weekly")
    assert r.status_code == 503


def test_engine_paused_skips_tick(monkeypatch):
    monkeypatch.setenv("AUTOREACH_ENGINE_PAUSED", "1")
    from engine.worker.celery_app import tick_all_active

    result = tick_all_active()
    assert result.get("paused") is True
    assert result.get("executed") == 0
