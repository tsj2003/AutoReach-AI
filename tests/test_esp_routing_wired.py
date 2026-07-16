"""ESP matching is wired into the live dispatch router (not just a stray module).

Gmail→Gmail / Outlook→Outlook improves primary-inbox placement. The router
should PREFER a same-ESP healthy mailbox, but ordering must never override the
health fail-safe.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine import Event, EventKind, open_storage
from engine.auth.mailbox_models import Mailbox
from engine.policies.esp_matcher import EspMatcher
from engine.services.mailbox_health import MailboxHealthMonitor
from engine.dispatch.router import SmartInboxRouter


class _StubMatcher:
    """Deterministic ESP detection (no DNS) — normalization stays real."""

    def __init__(self, target: str) -> None:
        self._target = target

    def detect_provider(self, email: str) -> str:
        return self._target

    def normalize_provider(self, value):
        return EspMatcher.normalize_provider(value)


def _seed(store, events, mailbox_id, *, provider, sent, bounced):
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(
        id=mailbox_id, tenant_id="t", email_address=f"{mailbox_id}@y.com",
        provider=provider, status="active", created_at=now, updated_at=now,
    ))
    for i in range(sent):
        events.emit(Event(id=f"{mailbox_id}-s{i}", kind=EventKind.EMAIL_SENT,
                          engagement_id="e", payload={"mailbox_id": mailbox_id}))
    for i in range(bounced):
        events.emit(Event(id=f"{mailbox_id}-b{i}", kind=EventKind.EMAIL_BOUNCED,
                          engagement_id="e", payload={"mailbox_id": mailbox_id}))


@pytest.mark.asyncio
async def test_router_prefers_same_esp_mailbox(tmp_path):
    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'esp.db'}")
    _seed(store, events, "mbx-outlook", provider="outlook", sent=10, bounced=0)
    _seed(store, events, "mbx-gmail", provider="gmail", sent=10, bounced=0)  # both healthy
    router = SmartInboxRouter(
        health_monitor=MailboxHealthMonitor(store=store, events=events),
        store=store,
        esp_matcher=_StubMatcher("google"),  # recipient is a Gmail address
    )
    chosen = await router.get_next_available_mailbox(
        tenant_id="t", recipient_email="buyer@gmail.com"
    )
    assert chosen.id == "mbx-gmail"  # same-ESP preferred even though outlook came first


@pytest.mark.asyncio
async def test_esp_preference_never_breaks_health_failsafe(tmp_path):
    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'esp2.db'}")
    # Same-ESP (gmail) mailbox is UNHEALTHY; the outlook one is healthy.
    _seed(store, events, "mbx-gmail", provider="gmail", sent=10, bounced=3)
    _seed(store, events, "mbx-outlook", provider="outlook", sent=10, bounced=0)
    router = SmartInboxRouter(
        health_monitor=MailboxHealthMonitor(store=store, events=events),
        store=store,
        esp_matcher=_StubMatcher("google"),
    )
    chosen = await router.get_next_available_mailbox(
        tenant_id="t", recipient_email="buyer@gmail.com"
    )
    # Prefers gmail, but it's unhealthy → falls through to the healthy outlook box.
    assert chosen.id == "mbx-outlook"


def test_normalize_provider_bridges_mailbox_and_esp_vocab():
    assert EspMatcher.normalize_provider("gmail") == "google"
    assert EspMatcher.normalize_provider("outlook") == "microsoft"
    assert EspMatcher.normalize_provider("smtp") == "other"
    assert EspMatcher.normalize_provider(None) == "other"
