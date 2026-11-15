"""US-001: Actions API — approve / reject / snooze / rerun on pending jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from cockpit import create_app
from engine.core.types import Job, JobKind


@pytest.fixture
def ctx(tmp_path):
    app = create_app(db_url=f"sqlite:///{tmp_path / 'act.db'}")
    client = TestClient(app, raise_server_exceptions=True)

    def signup(email):
        r = client.post("/api/auth/signup", json={"email": email, "password": "Password1!", "company_name": "Co"})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    owner = signup("owner-actions@x.co")
    cid = client.post("/api/campaigns", json={"customer_name": "A", "offer": "We help teams", "icp_description": "i"},
                      headers=owner).json()["id"]
    store = app.state.store

    def seed_job(jid="job-1"):
        store.save_job(Job(
            id=jid, engagement_id=cid, agent_id="agent-x", kind=JobKind.EMAIL_SEND,
            payload={"to_email": "buyer@t.co", "to_name": "Jo", "company": "Acme", "offer": "We help teams",
                     "subject_template": "quick question, {first_name}", "body_template": "Hi {first_name}, {offer}"},
            requires_approval=True, state="awaiting_approval",
            scheduled_for=datetime.now(timezone.utc),
        ))
        return jid

    return client, owner, cid, store, signup, seed_job


def test_approve(ctx):
    client, owner, cid, store, _, seed = ctx
    jid = seed()
    r = client.post(f"/api/campaigns/{cid}/approve-job/{jid}", headers=owner)
    assert r.status_code == 200, r.text
    assert r.json()["sent"] is True
    job = store.get_job(jid)
    assert job.state == "succeeded"
    assert "{first_name}" not in (job.payload.get("subject") or "")
    assert "Jo" in (job.payload.get("subject") or "")


def test_reject(ctx):
    client, owner, cid, store, _, seed = ctx
    jid = seed("job-r")
    r = client.post(f"/api/campaigns/{cid}/reject-job/{jid}", headers=owner)
    assert r.status_code == 200, r.text
    assert store.get_job(jid).state == "rejected"


def test_snooze_sets_until_and_keeps_awaiting(ctx):
    client, owner, cid, store, _, seed = ctx
    jid = seed("job-s")
    until = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = client.post(f"/api/campaigns/{cid}/snooze-job/{jid}", json={"until": until}, headers=owner)
    assert r.status_code == 200, r.text
    job = store.get_job(jid)
    assert job.state == "awaiting_approval"  # still in queue, just deferred
    assert job.payload.get("snoozed_until")


def test_rerun_redrafts_and_scores(ctx):
    client, owner, cid, store, _, seed = ctx
    jid = seed("job-rr")
    r = client.post(f"/api/campaigns/{cid}/rerun-job/{jid}", headers=owner)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "deliverability_risk" in body
    job = store.get_job(jid)
    assert job.state == "awaiting_approval"
    assert "deliverability_risk" in job.payload
    assert job.payload.get("subject")


def test_edit_updates_draft_and_rescores(ctx):
    client, owner, cid, store, _, seed = ctx
    jid = seed("job-e")
    r = client.post(f"/api/campaigns/{cid}/edit-job/{jid}",
                    json={"subject": "hand-edited subject", "body_text": "Short human note. Worth a chat?"},
                    headers=owner)
    assert r.status_code == 200, r.text
    assert "deliverability_risk" in r.json()
    job = store.get_job(jid)
    assert job.payload["subject"] == "hand-edited subject"
    assert job.payload["edited"] is True
    assert job.state == "awaiting_approval"


def test_actions_are_tenant_scoped(ctx):
    client, owner, cid, store, signup, seed = ctx
    jid = seed("job-t")
    intruder = signup("intruder-actions@x.co")
    until = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert client.post(f"/api/campaigns/{cid}/approve-job/{jid}", headers=intruder).status_code == 404
    assert client.post(f"/api/campaigns/{cid}/snooze-job/{jid}", json={"until": until}, headers=intruder).status_code == 404
    assert client.post(f"/api/campaigns/{cid}/rerun-job/{jid}", headers=intruder).status_code == 404


def test_actions_require_auth(ctx):
    client, _, cid, _, _, seed = ctx
    jid = seed("job-a")
    assert client.post(f"/api/campaigns/{cid}/rerun-job/{jid}").status_code == 401
