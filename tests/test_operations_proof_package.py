from datetime import datetime, timezone

from fastapi.testclient import TestClient


def _auth_app(tmp_path):
    from cockpit import create_app

    app = create_app(db_url=f"sqlite:///{tmp_path / 'proof_api.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "proof@example.com",
            "password": "Password1!",
            "company_name": "Proof Ops",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return app, client, body["tenant_id"], {"Authorization": f"Bearer {body['access_token']}"}


def test_proof_package_requires_tenant_ownership(tmp_path):
    _, client, _, headers = _auth_app(tmp_path)
    response = client.get("/api/operations/campaigns/missing/proof-package", headers=headers)
    assert response.status_code == 404


def test_proof_package_returns_roi_outcomes_and_traces(tmp_path):
    from engine.core.types import Engagement, Event, EventKind, Meeting

    app, client, tenant_id, headers = _auth_app(tmp_path)
    engagement = Engagement(
        id="cmp_proof",
        customer_name="Proof Campaign",
        offer="O",
        icp_description="I",
        price_per_outcome_cents=100000,
    )
    app.state.store.save_engagement(engagement, tenant_id=tenant_id)
    app.state.store.save_meeting(
        Meeting(
            id="mtg_qualified",
            engagement_id=engagement.id,
            prospect_id="prospect_1",
            reply_id=None,
            scheduled_for=datetime.now(timezone.utc),
            status="qualified",
            notes="Founder showed up and matched ICP.",
        )
    )
    app.state.events.emit(
        Event(
            id="evt_trace",
            kind=EventKind.MEETING_QUALIFIED,
            engagement_id=engagement.id,
            prospect_id="prospect_1",
            payload={"openinference_trace_id": "trace-proof-1"},
        )
    )

    response = client.get(
        f"/api/operations/campaigns/{engagement.id}/proof-package",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["campaign"]["id"] == "cmp_proof"
    assert data["economics"]["revenue_cents"] == 100000
    assert data["economics"]["qualified_count"] == 1
    assert data["outcomes"][0]["meeting_id"] == "mtg_qualified"
    assert data["trace_ids"] == ["trace-proof-1"]
