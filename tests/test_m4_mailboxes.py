"""M4 — DbTokenStore + mailbox storage + mailboxes API tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from engine import open_storage
from engine.adapters.db_token_store import DbTokenStore
from engine.adapters.gmail_token_store import TokenInvalid, TokenUnavailable
from engine.auth.mailbox_models import Mailbox


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path/'m4.db'}")


@pytest.fixture
def auth_client(tmp_path):
    from cockpit import create_app
    app = create_app(db_url=f"sqlite:///{tmp_path / 'm4api.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    r = client.post("/api/auth/signup", json={"email": "f@acme.com", "password": "Password1!", "company_name": "Acme"})
    return client, r.json()


# ── Mailbox storage ──────────────────────────────────────────────────────


def test_mailbox_roundtrip(storage):
    store, _, _ = storage
    now = datetime.now(timezone.utc)
    mb = Mailbox(
        id="mbx_1", tenant_id="t1", email_address="me@gmail.com",
        credentials_json={"token": "x", "refresh_token": "r"},
        created_at=now, updated_at=now,
    )
    store.save_mailbox(mb)
    fetched = store.get_mailbox("mbx_1")
    assert fetched.email_address == "me@gmail.com"
    assert fetched.credentials_json["token"] == "x"
    assert fetched.status == "active"


def test_list_mailboxes_by_tenant(storage):
    store, _, _ = storage
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(id="a", tenant_id="t1", email_address="a@x.com", created_at=now, updated_at=now))
    store.save_mailbox(Mailbox(id="b", tenant_id="t1", email_address="b@x.com", created_at=now, updated_at=now))
    store.save_mailbox(Mailbox(id="c", tenant_id="t2", email_address="c@x.com", created_at=now, updated_at=now))
    assert len(list(store.list_mailboxes("t1"))) == 2
    assert len(list(store.list_mailboxes("t2"))) == 1


def test_update_mailbox_status(storage):
    store, _, _ = storage
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(id="m", tenant_id="t", email_address="x@y.com", created_at=now, updated_at=now))
    store.update_mailbox_status("m", status="revoked", last_error="token gone")
    assert store.get_mailbox("m").status == "revoked"
    assert store.get_mailbox("m").last_error == "token gone"


# ── DbTokenStore ───────────────────────────────────────────────────────────


def test_db_token_store_unavailable_when_no_mailbox(storage):
    store, _, _ = storage
    ts = DbTokenStore(store=store, mailbox_id="nope")
    with pytest.raises(TokenUnavailable):
        ts.load()


def test_db_token_store_invalid_when_revoked(storage):
    store, _, _ = storage
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(id="m", tenant_id="t", email_address="x@y.com",
                               status="revoked", last_error="gone",
                               credentials_json={"token": "x"}, created_at=now, updated_at=now))
    ts = DbTokenStore(store=store, mailbox_id="m")
    with pytest.raises(TokenInvalid):
        ts.load()


def test_db_token_store_unavailable_when_no_credentials(storage):
    store, _, _ = storage
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(id="m", tenant_id="t", email_address="x@y.com",
                               credentials_json=None, created_at=now, updated_at=now))
    ts = DbTokenStore(store=store, mailbox_id="m")
    with pytest.raises(TokenUnavailable):
        ts.load()


def test_db_token_store_mark_invalid_updates_db(storage):
    store, _, _ = storage
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(id="m", tenant_id="t", email_address="x@y.com",
                               credentials_json={"token": "x"}, created_at=now, updated_at=now))
    ts = DbTokenStore(store=store, mailbox_id="m")
    ts.mark_invalid("test reason")
    assert ts.is_invalid() is True
    assert store.get_mailbox("m").status == "revoked"


# ── Mailboxes API ────────────────────────────────────────────────────────


def test_mailboxes_list_empty(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.get("/api/mailboxes", headers=h)
    assert r.status_code == 200
    assert r.json() == []


def test_mailboxes_connect_start_returns_auth_url(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-secret",
    }, headers=h)
    assert r.status_code == 200
    assert "accounts.google.com" in r.json()["authorization_url"]
    assert r.json()["state"]


def test_mailboxes_requires_auth(auth_client):
    client, _ = auth_client
    r = client.get("/api/mailboxes")
    assert r.status_code == 401


def test_mailbox_disconnect(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    # Seed a mailbox directly.
    app = client.app
    me = client.get("/api/auth/me", headers=h).json()
    now = datetime.now(timezone.utc)
    app.state.store.save_mailbox(Mailbox(
        id="mbx_x", tenant_id=me["tenant_id"], email_address="me@gmail.com",
        credentials_json={"token": "x"}, created_at=now, updated_at=now,
    ))
    r = client.get("/api/mailboxes", headers=h)
    assert len(r.json()) == 1
    r = client.delete("/api/mailboxes/mbx_x", headers=h)
    assert r.status_code == 204
    assert app.state.store.get_mailbox("mbx_x").status == "revoked"


def test_free_plan_blocks_second_mailbox(auth_client):
    import dataclasses
    client, tokens = auth_client
    app = client.app
    # New signups get a Pro trial; this test covers the free-tier cap, so
    # downgrade the tenant to free and re-login for a fresh token.
    tenant = app.state.store.get_tenant(tokens["tenant_id"])
    app.state.store.save_tenant(dataclasses.replace(tenant, plan="free", trial_ends_at=None))
    tokens = client.post("/api/auth/login", json={
        "email": "f@acme.com", "password": "Password1!",
    }).json()
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = client.get("/api/auth/me", headers=h).json()
    now = datetime.now(timezone.utc)
    # Seed one active mailbox (free plan cap = 1).
    app.state.store.save_mailbox(Mailbox(
        id="mbx_1", tenant_id=me["tenant_id"], email_address="one@gmail.com",
        credentials_json={"token": "x"}, created_at=now, updated_at=now,
    ))
    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "cid", "client_secret": "csec",
    }, headers=h)
    assert r.status_code == 403
