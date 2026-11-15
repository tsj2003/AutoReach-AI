"""Phase 5+ feature tests: webhook, enrichment, learning, reply wiring."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from cockpit import create_app
from engine import open_storage
from engine.core.types import CostEntry, Event, EventKind, Prospect, Reply
from engine.enrichment.models import EnrichmentRequest
from engine.enrichment.waterfall import EnrichmentWaterfall
from engine.learning.measurement import LearningMeasurementService
from engine.services.reply_actions import ReplyActionExecutor
from engine.signals.repository import SignalRepository
from engine.signals.webhook_auth import sign_payload
from engine.signals.webhook_client import webhook_request_headers


@pytest.fixture
def signals_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOREACH_SIGNALS_ENABLED", "1")
    return TestClient(create_app(db_url=f"sqlite:///{tmp_path / 'phase5.db'}"))


def _signup(client: TestClient) -> str:
    res = client.post(
        "/api/auth/signup",
        json={"email": "phase5@test.com", "password": "secret123", "company_name": "Phase5 Co"},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def test_webhook_create_and_ingest(signals_client):
    token = _signup(signals_client)
    headers = {"Authorization": f"Bearer {token}"}

    create = signals_client.post(
        "/api/signals/sources",
        headers=headers,
        json={"connector_kind": "webhook", "name": "CRM events"},
    )
    assert create.status_code == 200, create.text
    data = create.json()
    source_id = data["source_id"]
    secret = data["webhook_secret"]
    assert secret

    payload = {
        "signal_type": "funding_round",
        "company_domain": "acme.com",
        "company_name": "Acme Corp",
        "evidence": {"summary": "Raised Series B", "source_url": "https://acme.com/news"},
    }
    body = json.dumps(payload).encode()
    wh_headers = webhook_request_headers(secret, body, idempotency_key="phase5-evt-001")

    ok = signals_client.post(
        f"/api/webhooks/signals/{source_id}",
        content=body,
        headers=wh_headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["events_inserted"] >= 1

    bad = signals_client.post(
        f"/api/webhooks/signals/{source_id}",
        content=body,
        headers={
            **webhook_request_headers(secret, body, idempotency_key="phase5-bad"),
            "X-Attainly-Signature": "sha256=deadbeef",
        },
    )
    assert bad.status_code == 401


def test_webhook_secret_redacted_in_list(signals_client):
    token = _signup(signals_client)
    headers = {"Authorization": f"Bearer {token}"}
    signals_client.post(
        "/api/signals/sources",
        headers=headers,
        json={"connector_kind": "webhook", "name": "Hidden secret"},
    )
    listed = signals_client.get("/api/signals/sources", headers=headers).json()
    assert listed["sources"][0]["config"]["webhook_secret"] == "***"


def test_enrichment_waterfall_profile_data(tmp_path):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path / 'enr.db'}")
    wf = EnrichmentWaterfall()
    req = EnrichmentRequest(
        tenant_id="t1",
        prospect_id="p1",
        email="ceo@acme.com",
        company_domain="acme.com",
        company_name="Acme",
        full_name="CEO",
    )
    result = wf.enrich(req, profile={"email": "ceo@acme.com", "company": "Acme"})
    assert result.fields.get("email") == "ceo@acme.com"
    assert "profile_data" in result.providers_attempted


def test_learning_insufficient_data(tmp_path):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path / 'learn.db'}")
    svc = LearningMeasurementService(store=store, events=events)
    report = svc.weekly_report(tenant_id="any")
    assert report.enough_data is False
    assert any(i.confidence == "insufficient" for i in report.insights)


def test_reply_action_executor_flags_interested(tmp_path):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path / 'reply.db'}")
    reply = Reply(
        id="rep1",
        engagement_id="eng1",
        prospect_id="pros1",
        job_id=None,
        snippet="Sounds good",
        classification="interested",
        suggested_reply="Great — here's a link",
        status="pending",
    )
    ex = ReplyActionExecutor(store=store, events=events)
    result = ex.handle(reply, mode="hitl")
    assert result.action == "flagged_for_approval"


def test_mcp_client_not_configured():
    import asyncio
    from engine.integrations.mcp_client import RealMCPClient

    client = RealMCPClient()
    assert client.is_configured() is False
    assert asyncio.run(client.connect()) is False
    assert asyncio.run(client.discover_tools()) == []


def test_mcp_client_http_url_not_implemented():
    import asyncio
    from engine.integrations.mcp_client import RealMCPClient

    client = RealMCPClient(server_url="http://localhost:3000")
    assert client.is_configured() is True
    assert asyncio.run(client.connect()) is False


@pytest.mark.asyncio
async def test_crm_sync_fails_without_real_server():
    from engine.workflows.crm_sync import CRMSyncAgent
    from engine.runtime.context import TenantContext

    ctx = TenantContext(
        tenant_id="t1",
        campaign_id="c1",
        variables={"mcp_server_url": "http://localhost:3000"},
        encrypted_secrets={},
    )
    agent = CRMSyncAgent()
    result = await agent.sync_outcome(ctx, "test@example.com", "MEETING", "notes")
    assert result is False
