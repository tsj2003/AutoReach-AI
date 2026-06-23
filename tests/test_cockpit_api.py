import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from cockpit.main import app


client = TestClient(app)


def test_api_requires_tenant_header():
    """Forces strict X-Tenant-ID header validation on all routes."""
    response = client.get("/api/v1/outbox/pending")
    assert response.status_code == 400
    assert "X-Tenant-ID header is required" in response.text


@patch("cockpit.api.outbox.db_session")
def test_fetch_pending_jobs_is_tenant_isolated(mock_db):
    """Ensures a tenant can only see their own PENDING_APPROVAL jobs."""
    mock_job = MagicMock()
    mock_job.id = "job-123"
    mock_job.payload = {"subject": "Quick question"}
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_job]

    response = client.get("/api/v1/outbox/pending", headers={"X-Tenant-ID": "t-alpha"})

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
    """Forces the approve endpoint to transition state and trigger Celery dispatch."""
    mock_job = MagicMock()
    mock_job.tenant_id = "t-alpha"
    mock_job.status = "PENDING_APPROVAL"
    mock_job.payload = {"subject": "Quick question"}
    mock_db.query.return_value.filter.return_value.first.return_value = mock_job

    response = client.post("/api/v1/outbox/job-123/approve", headers={"X-Tenant-ID": "t-alpha"})

    assert response.status_code == 200
    assert mock_job.status == "APPROVED"
    mock_db.commit.assert_called_once()

    mock_dispatch.assert_called_once()
    assert mock_dispatch.call_args.kwargs["queue"] == "standard-agents"


@patch("cockpit.api.outbox.db_session")
def test_reject_job_halts_execution(mock_db):
    """Forces the reject endpoint to transition state to REJECTED."""
    mock_job = MagicMock()
    mock_job.tenant_id = "t-alpha"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_job

    response = client.post("/api/v1/outbox/job-123/reject", headers={"X-Tenant-ID": "t-alpha"})

    assert response.status_code == 200
    assert mock_job.status == "REJECTED"
    mock_db.commit.assert_called_once()
