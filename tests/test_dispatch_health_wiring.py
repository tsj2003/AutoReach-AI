"""The dispatch router's health gate must reflect REAL event-log signals.

Regression for the "smart dispatch" gap: `get_health` (what
SmartInboxRouter.get_next_available_mailbox calls) previously read process-memory
counters that reset every worker restart and never saw cross-process sends. It
must now return the durable, events-based health when a store + event log are
wired, and route away from an unhealthy mailbox.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine import Event, EventKind, open_storage
from engine.auth.mailbox_models import Mailbox
from engine.services.mailbox_health import MailboxHealthMonitor
from engine.dispatch.router import SmartInboxRouter


def _seed(store, events, mailbox_id, *, sent, bounced):
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(
        id=mailbox_id, tenant_id="t", email_address=f"{mailbox_id}@y.com",
        status="active", created_at=now, updated_at=now,
    ))
    for i in range(sent):
        events.emit(Event(id=f"{mailbox_id}-s{i}", kind=EventKind.EMAIL_SENT,
                          engagement_id="e", payload={"mailbox_id": mailbox_id}))
    for i in range(bounced):
        events.emit(Event(id=f"{mailbox_id}-b{i}", kind=EventKind.EMAIL_BOUNCED,
                          engagement_id="e", payload={"mailbox_id": mailbox_id}))


@pytest.mark.asyncio
async def test_get_health_uses_real_events_when_wired(tmp_path):
    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'h.db'}")
    _seed(store, events, "m-bad", sent=10, bounced=3)  # 30% bounce → unhealthy
    monitor = MailboxHealthMonitor(store=store, events=events)
    status = await monitor.get_health("m-bad")
    assert status.status == "PAUSED_SAFETY"
    assert status.healthy is False


@pytest.mark.asyncio
async def test_router_routes_away_from_unhealthy_mailbox(tmp_path):
    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'r.db'}")
    _seed(store, events, "m-bad", sent=10, bounced=3)   # unhealthy
    _seed(store, events, "m-good", sent=10, bounced=0)  # healthy
    monitor = MailboxHealthMonitor(store=store, events=events)
    router = SmartInboxRouter(health_monitor=monitor, store=store)
    chosen = await router.get_next_available_mailbox(tenant_id="t")
    assert chosen is not None
    assert chosen.id == "m-good"


@pytest.mark.asyncio
async def test_router_fails_safe_when_all_unhealthy(tmp_path):
    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'r2.db'}")
    _seed(store, events, "m1", sent=10, bounced=3)
    _seed(store, events, "m2", sent=10, bounced=4)
    monitor = MailboxHealthMonitor(store=store, events=events)
    router = SmartInboxRouter(health_monitor=monitor, store=store)
    chosen = await router.get_next_available_mailbox(tenant_id="t")
    assert chosen is None  # fail safe: don't send through an unhealthy mailbox
