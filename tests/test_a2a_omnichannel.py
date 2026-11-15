import pytest
from unittest.mock import AsyncMock, patch, MagicMock
# Cursor will implement the coordinator and the new provider
from engine.workflows.coordinator import OmnichannelCoordinator
from engine.dispatch.linkedin import LinkedInProvider
from engine.core.types import TenantContext


@pytest.fixture
def sample_tenant():
    return TenantContext(
        tenant_id="t-omni-1",
        campaign_id="cmp-omni-1",
        variables={"linkedin_enabled": True},
        encrypted_secrets={"li_session_token": "enc_li_123"}
    )


@pytest.mark.asyncio
@patch("engine.workflows.coordinator.dispatch_agent_task.apply_async")
async def test_coordinator_fans_out_a2a_tasks(mock_dispatch, sample_tenant):
    """
    Forces the Coordinator to act as a manager, delegating work
    to both the Email Agent and the LinkedIn Agent in parallel.
    """
    coordinator = OmnichannelCoordinator()

    # Act: The ingestor passes a fresh high-intent prospect to the coordinator
    await coordinator.plan_and_dispatch(
        tenant_context=sample_tenant,
        prospect_id="p-omni-999",
        signal_data={"type": "funding_round", "amount": 10000000}
    )

    # Assert: The coordinator must have dispatched exactly two Celery tasks
    assert mock_dispatch.call_count == 2

    # Extract the task names from the Celery dispatch calls
    dispatched_tasks = [call.kwargs["args"][0] for call in mock_dispatch.call_args_list]

    # Verify the exact agents that were invoked
    assert "draft_email_touch" in dispatched_tasks
    assert "draft_linkedin_connection" in dispatched_tasks

    # Verify they were routed to the standard worker queues
    assert mock_dispatch.call_args_list[0].kwargs["queue"] == "standard-agents"
    assert mock_dispatch.call_args_list[1].kwargs["queue"] == "standard-agents"


@pytest.mark.asyncio
async def test_coordinator_skips_linkedin_if_disabled():
    """Ensures the coordinator respects tenant campaign settings for channels."""
    ctx_email_only = TenantContext(
        tenant_id="t-omni-2", campaign_id="cmp-omni-2",
        variables={"linkedin_enabled": False}, encrypted_secrets={}
    )
    coordinator = OmnichannelCoordinator()

    with patch("engine.workflows.coordinator.dispatch_agent_task.apply_async") as mock_dispatch:
        await coordinator.plan_and_dispatch(ctx_email_only, "p-omni-888", {})

        # Assert: Should ONLY dispatch the email agent
        assert mock_dispatch.call_count == 1
        assert mock_dispatch.call_args.kwargs["args"][0] == "draft_email_touch"


@pytest.mark.asyncio
async def test_linkedin_provider_interface():
    """Defines the strict dispatch contract for the LinkedIn executor."""
    # We don't implement the actual scraping/API logic yet, just the boundary
    provider = LinkedInProvider(session_token="mock_token")

    with patch.object(provider, "send_connection_request", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        # Act
        result = await provider.send_connection_request(
            profile_url="https://linkedin.com/in/target",
            message="Saw the recent Series A—congrats! Let's connect."
        )

        # Assert
        assert result is True
        mock_send.assert_called_once_with(
            profile_url="https://linkedin.com/in/target",
            message="Saw the recent Series A—congrats! Let's connect."
        )
