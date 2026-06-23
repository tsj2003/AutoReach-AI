import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from engine.services.mailbox_health import HealthStatus
from engine import Engagement, Job, JobKind, open_storage
from engine.auth.mailbox_models import Mailbox
from engine.dispatch.adapter import SmartRoutedEmailAdapter
from engine.dispatch.router import SmartInboxRouter
from engine.dispatch.provider import SMTPProvider
from engine.runtime.results import AdapterResultData


@pytest.fixture
def mock_health_monitor():
    """Mocks the Redis health backend to simulate live deliverability states."""
    monitor = AsyncMock()

    async def mock_get_health(mbx_id):
        if mbx_id == "mbx-burned":
            return HealthStatus(bounce_rate=0.08, status="PAUSED_SAFETY")
        return HealthStatus(bounce_rate=0.01, status="HEALTHY")

    monitor.get_health.side_effect = mock_get_health
    return monitor


@pytest.mark.asyncio
@patch("engine.dispatch.router.db_session")
async def test_router_selects_healthy_mailbox_and_skips_burned(mock_db, mock_health_monitor):
    """Forces the router to query Redis and strictly bypass PAUSED_SAFETY mailboxes."""
    mock_burned = MagicMock(id="mbx-burned")
    mock_healthy = MagicMock(id="mbx-healthy")

    mock_db.query.return_value.filter.return_value.all.return_value = [mock_burned, mock_healthy]

    router = SmartInboxRouter(health_monitor=mock_health_monitor)

    selected_mailbox = await router.get_next_available_mailbox(tenant_id="t-dispatch-99")

    assert selected_mailbox is not None
    assert selected_mailbox.id == "mbx-healthy"


@pytest.mark.asyncio
@patch.object(SMTPProvider, "send_email", new_callable=AsyncMock)
async def test_router_logs_send_to_redis_after_dispatch(mock_send, mock_health_monitor):
    """Ensures the router closes the loop by incrementing the Redis rolling window."""
    mock_send.return_value = True
    router = SmartInboxRouter(health_monitor=mock_health_monitor)

    success = await router.dispatch_email(
        mailbox_id="mbx-healthy",
        payload={"to": "ceo@startup.com", "subject": "Funding round", "body": "Hey..."},
    )

    assert success is True
    mock_send.assert_called_once()
    mock_health_monitor.log_sent.assert_called_once_with("mbx-healthy")


@pytest.mark.asyncio
async def test_provider_uses_db_mailbox_token_store_and_normalizes_payload():
    """The production provider must reuse the real Gmail adapter with a per-mailbox token store."""
    mailbox = MagicMock(
        id="mbx-prod",
        email_address="founder@client.com",
        status="active",
    )
    store = MagicMock()
    store.get_mailbox.return_value = mailbox
    captured = {}

    class FakeAdapter:
        def __init__(self, *, sender_email, token_store, dry_run):
            captured["sender_email"] = sender_email
            captured["token_store"] = token_store
            captured["dry_run"] = dry_run

        def execute(self, job, *, context):
            captured["job"] = job
            captured["context"] = context
            return AdapterResultData.ok(sent=True, dry_run=False)

    provider = SMTPProvider(
        store=store,
        events=MagicMock(),
        ledger=MagicMock(),
        gmail_adapter_factory=FakeAdapter,
        dry_run=False,
    )

    sent = await provider.send_email(
        mailbox_id="mbx-prod",
        payload={
            "to": "ceo@startup.com",
            "subject": "Funding round",
            "body": "Congrats on the round.",
            "campaign_id": "cmp-1",
        },
    )

    assert sent is True
    assert captured["sender_email"] == "founder@client.com"
    assert captured["token_store"].mailbox_id == "mbx-prod"
    assert captured["job"].payload["to_email"] == "ceo@startup.com"
    assert captured["job"].payload["body_text"] == "Congrats on the round."
    assert captured["job"].engagement_id == "cmp-1"


def test_smart_routed_adapter_sends_runtime_job_through_tenant_mailbox(tmp_path):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path / 'smart_adapter.db'}")
    store.save_engagement(
        Engagement(
            id="cmp-smart",
            customer_name="Smart",
            offer="Offer",
            icp_description="ICP",
        ),
        tenant_id="t-smart",
    )
    store.save_mailbox(
        Mailbox(
            id="mbx-smart",
            tenant_id="t-smart",
            email_address="seller@example.com",
            status="active",
        )
    )
    provider = MagicMock()
    provider.send_email = AsyncMock(return_value=True)
    adapter = SmartRoutedEmailAdapter(store=store, events=events, ledger=ledger, provider=provider)
    job = Job(
        id="job-smart",
        engagement_id="cmp-smart",
        agent_id="agent-smart",
        kind=JobKind.EMAIL_SEND,
        payload={
            "to_email": "buyer@example.com",
            "subject": "Quick question",
            "body_text": "Hello",
        },
    )

    result = adapter.execute(job, context=MagicMock())

    assert result.succeeded is True
    assert result.output["mailbox_id"] == "mbx-smart"
    provider.send_email.assert_called_once()
    payload = provider.send_email.call_args.kwargs["payload"]
    assert payload["tenant_id"] == "t-smart"
    assert payload["mailbox_id"] == "mbx-smart"
    assert payload["job_id"] == "job-smart"


def test_smart_routed_adapter_fails_closed_without_healthy_mailbox(tmp_path):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path / 'smart_adapter_empty.db'}")
    store.save_engagement(
        Engagement(
            id="cmp-empty",
            customer_name="Empty",
            offer="Offer",
            icp_description="ICP",
        ),
        tenant_id="t-empty",
    )
    adapter = SmartRoutedEmailAdapter(store=store, events=events, ledger=ledger)
    job = Job(
        id="job-empty",
        engagement_id="cmp-empty",
        agent_id="agent-empty",
        kind=JobKind.EMAIL_SEND,
        payload={"to_email": "buyer@example.com", "subject": "Hello", "body_text": "Body"},
    )

    result = adapter.execute(job, context=MagicMock())

    assert result.succeeded is False
    assert result.error == "no healthy mailbox available for tenant"
    assert result.retryable is True
