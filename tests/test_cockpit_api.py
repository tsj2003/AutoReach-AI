import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from cockpit.main import app
from engine.auth.jwt_handler import sign_jwt


client = TestClient(app)


def _auth_header(tenant_id: str) -> dict[str, str]:
    """Mint a real signed JWT so tenant is proven, not client-asserted."""
    token = sign_jwt(
        user_id="u-1",
        tenant_id=tenant_id,
        email="owner@example.com",
        role="owner",
        plan="pro",
    )
    return {"Authorization": f"Bearer {token}"}


def test_api_requires_authentication():
    """Approving a job dispatches a real send — it must require auth.

    Previously these routes trusted an X-Tenant-ID header with no auth, so any
    caller could approve/dispatch sends for any tenant. Tenant is now derived
    from the signed JWT.
    """
    response = client.get("/api/v1/outbox/pending")
    assert response.status_code == 401


def test_pending_rejects_header_spoofing():
    """A raw X-Tenant-ID header must NOT grant access without a valid token."""
    response = client.get(
        "/api/v1/outbox/pending", headers={"X-Tenant-ID": "t-victim"}
    )
    assert response.status_code == 401


@patch("cockpit.api.outbox.db_session")
def test_fetch_pending_jobs_is_tenant_isolated(mock_db):
    """A tenant only sees their own PENDING_APPROVAL jobs; scope comes from JWT."""
    mock_job = MagicMock()
    mock_job.id = "job-123"
    mock_job.payload = {"subject": "Quick question"}
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_job]

    response = client.get("/api/v1/outbox/pending", headers=_auth_header("t-alpha"))

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "job-123"

    call_args = str(mock_db.query.return_value.filter.call_args)
    assert "t-alpha" in call_args
    assert "PENDING_APPROVAL" in call_args


@patch("cockpit.api.outbox.dispatch_agent_task.apply_async")
@patch("cockpit.api.outbox.db_session")
def test_approve_job_triggers_dispatch(mock_db, mock_dispatch):
    """Approve transitions state and triggers Celery dispatch under the JWT tenant."""
    mock_job = MagicMock()
    mock_job.tenant_id = "t-alpha"
    mock_job.status = "PENDING_APPROVAL"
    mock_job.payload = {"subject": "Quick question"}
    mock_db.query.return_value.filter.return_value.first.return_value = mock_job

    response = client.post(
        "/api/v1/outbox/job-123/approve", headers=_auth_header("t-alpha")
    )

    assert response.status_code == 200
    assert mock_job.status == "APPROVED"
    mock_db.commit.assert_called_once()

    mock_dispatch.assert_called_once()
    assert mock_dispatch.call_args.kwargs["queue"] == "standard-agents"


@patch("cockpit.api.outbox.db_session")
def test_reject_job_halts_execution(mock_db):
    """Reject transitions state to REJECTED under the JWT tenant."""
    mock_job = MagicMock()
    mock_job.tenant_id = "t-alpha"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_job

    response = client.post(
        "/api/v1/outbox/job-123/reject", headers=_auth_header("t-alpha")
    )

    assert response.status_code == 200
    assert mock_job.status == "REJECTED"
    mock_db.commit.assert_called_once()
