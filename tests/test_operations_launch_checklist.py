from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch


def _auth_app(tmp_path):
    from cockpit import create_app

    app = create_app(db_url=f"sqlite:///{tmp_path / 'launch_api.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "launch@example.com",
            "password": "Password1!",
            "company_name": "Launch Ops",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return app, client, body["tenant_id"], {"Authorization": f"Bearer {body['access_token']}"}


def _save_campaign(app, tenant_id, *, ready=False):
    from engine.auth.mailbox_models import Mailbox
    from engine.core.types import Agent, Engagement

    metadata = {}
    monthly_budget_cents = None
    if ready:
        metadata = {
            "client_cure": "Turns fresh funding rounds into qualified sales meetings.",
            "deliverability_preflight": {"is_safe_to_send": True},
            "signal_matrix": {"allowed_signal_types": ["funding_round"]},
        }
        monthly_budget_cents = 500000
        app.state.store.save_mailbox(
            Mailbox(id="mbx_launch", tenant_id=tenant_id, email_address="ops@example.com")
        )

    engagement = Engagement(
        id="cmp_launch",
        customer_name="Launch Campaign",
        offer="Outcome engine",
        icp_description="B2B founders",
        monthly_budget_cents=monthly_budget_cents,
        status="paused",
        metadata=metadata,
    )
    app.state.store.save_engagement(engagement, tenant_id=tenant_id)
    if ready:
        app.state.store.save_agent(
            Agent(
                id="agt_launch",
                engagement_id=engagement.id,
                runner_kind="outbound.v1",
                config={"hitl_threshold": 50},
            ),
            tenant_id=tenant_id,
        )
    return engagement.id


def test_launch_checklist_blocks_unsafe_campaign(tmp_path):
    app, client, tenant_id, headers = _auth_app(tmp_path)
    campaign_id = _save_campaign(app, tenant_id, ready=False)

    response = client.get(
        f"/api/operations/campaigns/{campaign_id}/launch-checklist",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_launch_ready"] is False
    failed_keys = {item["key"] for item in data["items"] if not item["passed"]}
    assert {"dns_preflight", "client_cure", "mailbox_ready", "budget_guardrail", "signal_matrix", "hitl_configured"} <= failed_keys

    activate = client.post(
        f"/api/operations/campaigns/{campaign_id}/activate",
        headers=headers,
    )
    assert activate.status_code == 409


def test_launch_checklist_activates_ready_campaign(tmp_path):
    app, client, tenant_id, headers = _auth_app(tmp_path)
    campaign_id = _save_campaign(app, tenant_id, ready=True)

    response = client.post(
        f"/api/operations/campaigns/{campaign_id}/activate",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["is_launch_ready"] is True
    assert app.state.store.get_engagement(campaign_id, tenant_id=tenant_id).status == "active"


@patch("cockpit.api.operations.DeliverabilityPreflight.verify_domain", new_callable=AsyncMock)
def test_campaign_preflight_endpoint_stamps_campaign_metadata(mock_verify, tmp_path):
    from cockpit.services.preflight import PreflightResult

    mock_verify.return_value = PreflightResult(is_safe_to_send=True, failure_reasons=[])
    app, client, tenant_id, headers = _auth_app(tmp_path)
    campaign_id = _save_campaign(app, tenant_id, ready=False)

    response = client.post(
        f"/api/operations/campaigns/{campaign_id}/deliverability-preflight",
        headers=headers,
        json={"domain": "Outbound.Example."},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == tenant_id
    assert data["campaign_id"] == campaign_id
    assert data["domain"] == "outbound.example"
    assert data["is_safe_to_send"] is True
    mock_verify.assert_awaited_once_with("outbound.example")

    engagement = app.state.store.get_engagement(campaign_id, tenant_id=tenant_id)
    preflight = engagement.metadata["deliverability_preflight"]
    assert preflight["domain"] == "outbound.example"
    assert preflight["is_safe_to_send"] is True
    assert preflight["failure_reasons"] == []

    checklist = client.get(
        f"/api/operations/campaigns/{campaign_id}/launch-checklist",
        headers=headers,
    ).json()
    dns_item = next(item for item in checklist["items"] if item["key"] == "dns_preflight")
    assert dns_item["passed"] is True


@patch("cockpit.api.operations.DeliverabilityPreflight.verify_domain", new_callable=AsyncMock)
def test_campaign_preflight_endpoint_is_tenant_isolated(mock_verify, tmp_path):
    from cockpit.services.preflight import PreflightResult

    mock_verify.return_value = PreflightResult(is_safe_to_send=True, failure_reasons=[])
    _app, client, _tenant_id, owner_headers = _auth_app(tmp_path)
    campaign_id = client.post(
        "/api/campaigns",
        headers=owner_headers,
        json={
            "customer_name": "Tenant Scoped",
            "offer": "Outcome engine",
            "icp_description": "B2B founders",
        },
    ).json()["id"]

    intruder = client.post(
        "/api/auth/signup",
        json={
            "email": "intruder@example.com",
            "password": "Password1!",
            "company_name": "Intruder Co",
        },
    )
    intruder_headers = {"Authorization": f"Bearer {intruder.json()['access_token']}"}

    response = client.post(
        f"/api/operations/campaigns/{campaign_id}/deliverability-preflight",
        headers=intruder_headers,
        json={"domain": "outbound.example"},
    )

    assert response.status_code == 404
    mock_verify.assert_not_awaited()
