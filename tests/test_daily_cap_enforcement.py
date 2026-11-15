"""Daily send cap must actually be enforced — a real domain-safety guarantee.

The router gates on emails_sent_today >= max_emails_per_day, but the counter was
never incremented, so the cap never fired and the system could over-send without
limit (a fast way to burn a mailbox's domain in a pilot). Sends now bump the
counter atomically, so the cap holds.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine import open_storage
from engine.auth.mailbox_models import Mailbox
from engine.services.mailbox_health import MailboxHealthMonitor
from engine.dispatch.router import SmartInboxRouter


class _StubProvider:
    async def send_email(self, *, mailbox_id, payload):
        return True


def _seed(store, mailbox_id, *, cap):
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(
        id=mailbox_id, tenant_id="t", email_address=f"{mailbox_id}@y.com",
        provider="gmail", status="active", max_emails_per_day=cap,
        emails_sent_today=0, created_at=now, updated_at=now,
    ))


@pytest.mark.asyncio
async def test_daily_cap_is_enforced_after_sends(tmp_path):
    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'cap.db'}")
    _seed(store, "mbx", cap=2)
    router = SmartInboxRouter(
        health_monitor=MailboxHealthMonitor(store=store, events=events),
        provider=_StubProvider(),
        store=store,
    )

    # Under cap → selectable.
    assert (await router.get_next_available_mailbox(tenant_id="t")).id == "mbx"

    await router.dispatch_email(mailbox_id="mbx", payload={"to": "a@x.co"})
    assert store.get_mailbox("mbx").emails_sent_today == 1
    assert (await router.get_next_available_mailbox(tenant_id="t")).id == "mbx"  # still 1<2

    await router.dispatch_email(mailbox_id="mbx", payload={"to": "b@x.co"})
    assert store.get_mailbox("mbx").emails_sent_today == 2

    # Cap reached → no longer selectable (fail safe rather than over-send).
    assert await router.get_next_available_mailbox(tenant_id="t") is None


@pytest.mark.asyncio
async def test_send_count_not_bumped_on_failed_send(tmp_path):
    class _FailProvider:
        async def send_email(self, *, mailbox_id, payload):
            return False

    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'cap2.db'}")
    _seed(store, "mbx", cap=5)
    router = SmartInboxRouter(
        health_monitor=MailboxHealthMonitor(store=store, events=events),
        provider=_FailProvider(),
        store=store,
    )
    await router.dispatch_email(mailbox_id="mbx", payload={"to": "a@x.co"})
    assert store.get_mailbox("mbx").emails_sent_today == 0  # only successful sends count
