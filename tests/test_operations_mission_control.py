from fastapi.testclient import TestClient


def _auth_app(tmp_path):
    from cockpit import create_app

    app = create_app(db_url=f"sqlite:///{tmp_path / 'mission_api.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "mission@example.com",
            "password": "Password1!",
            "company_name": "Mission Ops",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return app, client, body["tenant_id"], {"Authorization": f"Bearer {body['access_token']}"}


def test_mission_control_requires_auth(tmp_path):
    _, client, _, _ = _auth_app(tmp_path)
    response = client.get("/api/operations/mission-control")
    assert response.status_code == 401


def test_mission_control_summarizes_tenant_ops(tmp_path):
    from datetime import datetime, timezone
    from engine.auth.mailbox_models import Mailbox
    from engine.core.types import Engagement, Job, JobKind, Meeting

    app, client, tenant_id, headers = _auth_app(tmp_path)
    engagement = Engagement(
        id="cmp_mission",
        customer_name="Mission Campaign",
        offer="O",
        icp_description="I",
        status="paused",
    )
    app.state.store.save_engagement(engagement, tenant_id=tenant_id)
    app.state.store.save_job(
        Job(
            id="job_approval",
            engagement_id=engagement.id,
            agent_id="agt_missing",
            kind=JobKind.EMAIL_SEND,
            payload={"subject": "Review"},
            state="awaiting_approval",
            requires_approval=True,
        )
    )
    app.state.store.save_mailbox(
        Mailbox(id="mbx_active", tenant_id=tenant_id, email_address="active@example.com", status="active")
    )
    app.state.store.save_mailbox(
        Mailbox(id="mbx_paused", tenant_id=tenant_id, email_address="paused@example.com", status="paused")
    )
    app.state.store.save_meeting(
        Meeting(
            id="mtg_qualified",
            engagement_id=engagement.id,
            prospect_id="prospect_1",
            reply_id=None,
            scheduled_for=datetime.now(timezone.utc),
            status="qualified",
        )
    )

    response = client.get("/api/operations/mission-control", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["campaign_count"] == 1
    assert data["pending_approval_count"] == 1
    assert data["booked_meeting_count"] == 1
    assert data["blocked_launch_count"] == 1
    assert data["mailbox_counts"]["active"] == 1
    assert data["mailbox_counts"]["paused"] == 1
    assert data["blocked_launches"][0]["campaign_id"] == "cmp_mission"
