"""US-003: reasoning fields on prospect + job payloads (evidence, guardian, trace)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from cockpit import create_app
from engine.core.types import Job, JobKind, Prospect


@pytest.fixture
def ctx(tmp_path):
    app = create_app(db_url=f"sqlite:///{tmp_path / 'reason.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    r = client.post("/api/auth/signup", json={"email": "r3@x.co", "password": "Password1!", "company_name": "Co"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    cid = client.post("/api/campaigns", json={
        "customer_name": "A", "offer": "We help teams", "icp_description": "i",
        "allowed_signal_types": ["funding_round", "hiring_surge"], "min_signal_stack": 2,
    }, headers=h).json()["id"]
    return client, h, cid, app.state.store


def test_prospect_detail_includes_signal_stack(ctx):
    client, h, cid, _ = ctx
    r = client.post(f"/api/campaigns/{cid}/signals/simulate", json={"signals": [
        {"signal_type": "funding_round", "company_domain": "hot.com", "payload": {"company": "Hot Co", "contact_email": "ceo@hot.com"}},
        {"signal_type": "hiring_surge", "company_domain": "hot.com", "payload": {"company": "Hot Co"}},
    ]}, headers=h)
    pid = r.json()["prospects"][0]["id"]

    detail = client.get(f"/api/contacts/{pid}", headers=h)
    assert detail.status_code == 200, detail.text
    stack = detail.json()["signal_stack"]
    assert stack["depth"] == 2
    assert stack["score"] > 0
    assert {e["signal_type"] for e in stack["evidence"]} == {"funding_round", "hiring_surge"}


def test_job_payload_carries_reasoning_fields(ctx):
    client, h, cid, store = ctx
    store.save_prospect(Prospect(
        id="p-reason", engagement_id=cid, email="x@t.co", company="Acme", status="new",
        research={
            "signal_stack": {"depth": 2, "score": 60, "evidence": [
                {"signal_type": "funding_round", "company_domain": "acme.com", "summary": "funding_round detected for acme.com"},
            ]},
            "matched_intent_signal": {"openinference_trace_id": "trace-xyz"},
        },
    ))
    store.save_job(Job(
        id="job-reason", engagement_id=cid, agent_id="a", kind=JobKind.EMAIL_SEND,
        payload={"to_email": "x@t.co", "company": "Acme", "subject": "hi",
                 "deliverability_risk": {"level": "block", "score": 40, "issues": [], "ai_fingerprint": 0}},
        prospect_id="p-reason", requires_approval=True, state="awaiting_approval",
        scheduled_for=datetime.now(timezone.utc),
    ))

    r = client.get(f"/api/campaigns/{cid}", headers=h)
    assert r.status_code == 200, r.text
    job = next(j for j in r.json()["jobs_awaiting_approval"] if j["id"] == "job-reason")
    assert job["deliverability_risk"]["level"] == "block"
    assert job["signal_stack"]["depth"] == 2
    assert job["openinference_trace_id"] == "trace-xyz"
    assert job["hitl_reason"]  # block → forced-HITL reason surfaced


def test_prospect_detail_is_tenant_scoped(ctx):
    client, h, cid, store = ctx
    store.save_prospect(Prospect(id="p-x", engagement_id=cid, email="x@t.co", status="new"))
    # A second tenant in the SAME app must not read tenant A's prospect.
    intr = client.post("/api/auth/signup", json={"email": "intr3@x.co", "password": "Password1!", "company_name": "I"})
    ih = {"Authorization": f"Bearer {intr.json()['access_token']}"}
    r = client.get("/api/contacts/p-x", headers=ih)
    assert r.status_code == 403
