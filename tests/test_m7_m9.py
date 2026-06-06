"""M7 (orphaned replies) + M9 (mailbox health + warmup) tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from engine import Event, EventKind, open_storage
from engine.auth.mailbox_models import Mailbox
from engine.services.mailbox_health import MailboxHealthMonitor, WARMUP_RAMP


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path/'m79.db'}")


@pytest.fixture
def auth_client(tmp_path):
    from cockpit import create_app
    app = create_app(db_url=f"sqlite:///{tmp_path / 'm79api.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    r = client.post("/api/auth/signup", json={"email": "f@acme.com", "password": "Password1!", "company_name": "Acme"})
    return client, r.json()


# ── M9 warmup + health ──────────────────────────────────────────────────


def test_warmup_ramp_caps():
    store, events, _ = open_storage("sqlite:///:memory:")
    m = MailboxHealthMonitor(store=store, events=events)
    assert m.recommended_cap(0) == WARMUP_RAMP[0]
    assert m.recommended_cap(7) == WARMUP_RAMP[7]
    assert m.recommended_cap(100) == 200  # graduated


def test_health_healthy_when_low_bounce(storage):
    store, events, _ = storage
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(id="m", tenant_id="t", email_address="x@y.com", created_at=now, updated_at=now))
    for i in range(10):
        events.emit(Event(id=f"s{i}", kind=EventKind.EMAIL_SENT, engagement_id="e"))
    status = MailboxHealthMonitor(store=store, events=events).check_health("m")
    assert status.healthy is True
    assert status.bounce_rate == 0.0


def test_health_unhealthy_when_high_bounce(storage):
    store, events, _ = storage
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(id="m", tenant_id="t", email_address="x@y.com", created_at=now, updated_at=now))
    for i in range(10):
        events.emit(Event(id=f"s{i}", kind=EventKind.EMAIL_SENT, engagement_id="e"))
    for i in range(2):
        events.emit(Event(id=f"b{i}", kind=EventKind.EMAIL_BOUNCED, engagement_id="e"))
    mon = MailboxHealthMonitor(store=store, events=events)
    status = mon.check_health("m")
    assert status.healthy is False  # 2/10 = 20% > 5%
    assert mon.auto_pause_if_unhealthy("m") is True
    assert store.get_mailbox("m").status == "paused"


def test_warmup_tick_advances_day_and_cap(storage):
    store, events, _ = storage
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(id="m", tenant_id="t", email_address="x@y.com",
                               warmup_day=0, status="warming", created_at=now, updated_at=now))
    mon = MailboxHealthMonitor(store=store, events=events)
    advanced = mon.warmup_tick("t")
    assert advanced == 1
    mb = store.get_mailbox("m")
    assert mb.warmup_day == 1
    assert mb.max_emails_per_day == WARMUP_RAMP[1]


# ── M7 orphaned replies ───────────────────────────────────────────────────


def test_orphaned_reply_storage(storage):
    store, events, _ = storage
    store.save_orphaned_reply(
        id="orph_1", tenant_id="t1", from_email="colleague@target.com",
        from_name="Colleague", subject="Fwd: your email", snippet="forwarding this",
        external_message_id="gmail_fwd_1",
    )
    rows = store.list_orphaned_replies("t1")
    assert len(rows) == 1
    assert rows[0]["from_email"] == "colleague@target.com"
    # Dedup lookup
    assert store.get_orphaned_by_external_id("gmail_fwd_1") is not None


def test_orphaned_attach(storage):
    store, events, _ = storage
    from engine import Engagement, Prospect
    store.save_engagement(Engagement(id="e", customer_name="C", offer="O", icp_description="I"))
    store.save_prospect(Prospect(id="p", engagement_id="e", email="x@y.com"))
    store.save_orphaned_reply(id="orph_1", tenant_id="t1", from_email="c@t.com",
                              from_name=None, subject=None, snippet="hi",
                              external_message_id="m1")
    assert store.attach_orphaned_reply("orph_1", "p") is True
    # Now it's attached, not unmatched.
    assert len(store.list_orphaned_replies("t1", status="unmatched")) == 0
    assert len(store.list_orphaned_replies("t1", status="attached")) == 1


def test_orphaned_api_list_and_attach(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    app = client.app
    me = client.get("/api/auth/me", headers=h).json()
    tid = me["tenant_id"]

    # Create a campaign + prospect (so attach target exists + is tenant-owned).
    r = client.post("/api/campaigns", json={"customer_name": "C", "offer": "O", "icp_description": "I"}, headers=h)
    cid = r.json()["id"]
    p = app.state.ops.add_prospect(engagement_id=cid, email="real@target.com")

    # Seed an orphaned reply.
    app.state.store.save_orphaned_reply(
        id="orph_x", tenant_id=tid, from_email="fwd@target.com",
        from_name="Fwd", subject="Fwd", snippet="forwarded", external_message_id="m9",
    )

    r = client.get("/api/inbox/others", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.post("/api/inbox/others/orph_x/attach", json={"prospect_id": p.id}, headers=h)
    assert r.status_code == 200

    # Now unmatched list is empty.
    r = client.get("/api/inbox/others", headers=h)
    assert len(r.json()) == 0


def test_orphaned_ignore_endpoint(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    app = client.app
    me = client.get("/api/auth/me", headers=h).json()
    tid = me["tenant_id"]
    app.state.store.save_orphaned_reply(
        id="orph_ign", tenant_id=tid, from_email="noise@spam.com",
        from_name=None, subject=None, snippet="not relevant", external_message_id="m_ign",
    )
    # Visible in unmatched.
    assert len(client.get("/api/inbox/others", headers=h).json()) == 1
    # Ignore it.
    r = client.post("/api/inbox/others/orph_ign/ignore", headers=h)
    assert r.status_code == 200
    # Gone from the unmatched list.
    assert len(client.get("/api/inbox/others", headers=h).json()) == 0


def test_orphaned_ignore_is_tenant_scoped(auth_client, tmp_path):
    """A second tenant cannot ignore another tenant's orphaned reply."""
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    app = client.app
    me = client.get("/api/auth/me", headers=h).json()
    app.state.store.save_orphaned_reply(
        id="orph_t1", tenant_id=me["tenant_id"], from_email="x@y.com",
        from_name=None, subject=None, snippet="hi", external_message_id="m_t1",
    )
    # Second tenant.
    r2 = client.post("/api/auth/signup", json={"email": "other@evil.com", "password": "Password1!"})
    h2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    resp = client.post("/api/inbox/others/orph_t1/ignore", headers=h2)
    assert resp.status_code == 404  # not visible/owned → cannot ignore
