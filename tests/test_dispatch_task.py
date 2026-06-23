import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from engine.runtime.context import TenantContext
from engine.tasks import dispatch_email_send_task


@pytest.fixture
def tenant_context():
    return TenantContext(
        tenant_id="t-send",
        campaign_id="cmp-send",
        variables={},
        encrypted_secrets={},
    )


@pytest.mark.asyncio
@patch("engine.dispatch.provider.SMTPProvider.send_email", new_callable=AsyncMock)
@patch("engine.open_storage")
async def test_dispatch_task_selects_healthy_mailbox_and_sends(mock_open_storage, mock_send, tenant_context):
    mailbox = MagicMock(
        id="mbx-safe",
        status="active",
        max_emails_per_day=100,
        emails_sent_today=0,
    )
    store = MagicMock()
    store.list_mailboxes.return_value = [mailbox]
    events = MagicMock()
    ledger = MagicMock()
    mock_open_storage.return_value = (store, events, ledger)
    mock_send.return_value = True

    result = await dispatch_email_send_task(
        payload={
            "to": "buyer@example.com",
            "subject": "Quick question",
            "body": "Hello",
        },
        context=tenant_context,
    )

    assert result.success is True
    assert result.output["mailbox_id"] == "mbx-safe"
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["mailbox_id"] == "mbx-safe"
    assert call_kwargs["payload"]["tenant_id"] == "t-send"
    assert call_kwargs["payload"]["engagement_id"] == "cmp-send"


@pytest.mark.asyncio
@patch("engine.open_storage")
async def test_dispatch_task_fails_closed_without_healthy_mailbox(mock_open_storage, tenant_context):
    store = MagicMock()
    store.list_mailboxes.return_value = []
    mock_open_storage.return_value = (store, MagicMock(), MagicMock())

    result = await dispatch_email_send_task(
        payload={"to": "buyer@example.com", "subject": "Quick question", "body": "Hello"},
        context=tenant_context,
    )

    assert result.success is False
    assert result.error == "no healthy mailbox available for tenant"
