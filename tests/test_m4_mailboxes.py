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


def test_mailbox_credentials_encrypt_at_rest_when_key_configured(storage, monkeypatch):
    from engine.storage.sqlite import mailboxes_table
    from sqlalchemy import select

    key = "EFONWtQiHXh-5vpx9TVH0qCuVCkqUgJutdYjRM3J_iE="
    monkeypatch.setenv("AUTOREACH_CREDENTIAL_ENCRYPTION_KEY", key)
    store, _, _ = storage
    now = datetime.now(timezone.utc)
    mb = Mailbox(
        id="mbx_secret",
        tenant_id="t1",
        email_address="secure@gmail.com",
        credentials_json={"token": "plain-token", "refresh_token": "plain-refresh"},
        oauth_client_secret="plain-client-secret",
        created_at=now,
        updated_at=now,
    )

    store.save_mailbox(mb)

    with store._holder.conn() as c:
        row = c.execute(
            select(mailboxes_table).where(mailboxes_table.c.id == "mbx_secret")
        ).first()

    assert row.credentials_json["__autoreach_encrypted__"] is True
    assert "plain-token" not in str(row.credentials_json)
    assert row.oauth_client_secret.startswith("enc:v1:")
    assert "plain-client-secret" not in row.oauth_client_secret

    fetched = store.get_mailbox("mbx_secret")
    assert fetched.credentials_json["token"] == "plain-token"
    assert fetched.credentials_json["refresh_token"] == "plain-refresh"
    assert fetched.oauth_client_secret == "plain-client-secret"


def test_list_mailboxes_by_tenant(storage):
    store, _, _ = storage
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(id="a", tenant_id="t1", email_address="a@x.com", created_at=now, updated_at=now))
    store.save_mailbox(Mailbox(id="b", tenant_id="t1", email_address="b@x.com", created_at=now, updated_at=now))
    store.save_mailbox(Mailbox(id="c", tenant_id="t2", email_address="c@x.com", created_at=now, updated_at=now))
    assert len(list(store.list_mailboxes("t1"))) == 2
    assert len(list(store.list_mailboxes("t2"))) == 1


def test_list_all_mailboxes_crosses_tenants(storage):
    store, _, _ = storage
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(id="a", tenant_id="t1", email_address="a@x.com", status="active", created_at=now, updated_at=now))
    store.save_mailbox(Mailbox(id="b", tenant_id="t2", email_address="b@x.com", status="warming", created_at=now, updated_at=now))
    store.save_mailbox(Mailbox(id="c", tenant_id="t3", email_address="c@x.com", status="revoked", created_at=now, updated_at=now))

    assert {m.id for m in store.list_all_mailboxes()} == {"a", "b", "c"}
    assert {m.id for m in store.list_all_mailboxes(status="active")} == {"a"}


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


def test_mailboxes_connect_start_falls_back_to_env_credentials(auth_client, monkeypatch):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "env-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "env-client-secret")

    r = client.post("/api/mailboxes/connect/start", json={}, headers=h)

    assert r.status_code == 200
    assert "accounts.google.com" in r.json()["authorization_url"]
    assert "env-client-id.apps.googleusercontent.com" in r.json()["authorization_url"]


def test_mailboxes_connect_start_uses_public_base_redirect_in_production(auth_client, monkeypatch):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    monkeypatch.setenv("AUTOREACH_PUBLIC_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "env-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "env-client-secret")

    r = client.post("/api/mailboxes/connect/start", json={}, headers=h)

    assert r.status_code == 200
    auth_url = r.json()["authorization_url"]
    assert "accounts.google.com" in auth_url
    assert "app.example.com" in auth_url
    assert "127.0.0.1" not in auth_url


def test_mailboxes_connect_start_byoc_body_overrides_env(auth_client, monkeypatch):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "env-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "env-client-secret")

    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "byoc-client-id.apps.googleusercontent.com",
        "client_secret": "byoc-secret",
    }, headers=h)

    assert r.status_code == 200
    assert "byoc-client-id.apps.googleusercontent.com" in r.json()["authorization_url"]
    assert "env-client-id.apps.googleusercontent.com" not in r.json()["authorization_url"]


def test_mailboxes_connect_start_rejects_missing_credentials(auth_client, monkeypatch):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    r = client.post("/api/mailboxes/connect/start", json={}, headers=h)

    assert r.status_code == 400
    assert "GOOGLE_CLIENT_ID" in r.text


def test_mailboxes_connect_start_rejects_local_redirect_in_production(auth_client, monkeypatch):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")

    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-secret",
        "redirect_uri": "http://127.0.0.1:8765/api/mailboxes/connect/callback",
    }, headers=h)

    assert r.status_code == 400
    assert "HTTPS" in r.text


def test_mailboxes_connect_start_accepts_same_host_https_redirect_in_production(auth_client, monkeypatch):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")

    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-secret",
        "redirect_uri": "https://testserver/api/mailboxes/connect/callback",
    }, headers=h)

    assert r.status_code == 200
    assert "accounts.google.com" in r.json()["authorization_url"]
    assert r.json()["state"]


def test_mailboxes_connect_start_rejects_wrong_callback_path(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}

    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-secret",
        "redirect_uri": "http://127.0.0.1:8765/oauth/google/callback",
    }, headers=h)

    assert r.status_code == 400
    assert "mailbox callback path" in r.text


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

def test_mailboxes_connect_callback_access_denied_redirects_to_mailboxes(auth_client):
    client, _ = auth_client
    r = client.get(
        "/api/mailboxes/connect/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith("/app/operations/mailboxes?")
    assert "error=access_denied" in loc
    assert "oauth_error=access_denied" in loc


def test_mailboxes_connect_callback_invalid_state_redirects(auth_client):
    client, _ = auth_client
    r = client.get(
        "/api/mailboxes/connect/callback",
        params={"code": "abc", "state": "missing"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = r.headers["location"]
    assert "error=invalid_or_expired_state" in loc
    assert "oauth_error=invalid_or_expired_state" in loc


def test_pending_ctx_error_missing_secret_and_redirect():
    from cockpit.api.mailboxes import _pending_ctx_error
    assert _pending_ctx_error(None, "code") == "invalid_or_expired_state"
    assert _pending_ctx_error({"client_id": "cid", "client_secret": "", "redirect_uri": "https://x/api/mailboxes/connect/callback"}, "code") == "missing_client_secret"
    assert _pending_ctx_error({"client_id": "cid", "client_secret": "sec", "redirect_uri": ""}, "code") == "redirect_uri_mismatch"
    assert _pending_ctx_error({"client_id": "cid", "client_secret": "sec", "redirect_uri": "https://x/api/mailboxes/connect/callback"}, "code") is None


def test_mailbox_oauth_error_code_scope_change():
    from cockpit.api.mailboxes import _mailbox_oauth_error_code
    assert _mailbox_oauth_error_code(Warning('Scope has changed from "a" to "b".')) == "scope_mismatch"
    assert _mailbox_oauth_error_code(RuntimeError("invalid_grant")) == "invalid_or_expired_code"


def test_mailboxes_connect_callback_token_failure_redirects_not_500(auth_client, monkeypatch):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-secret",
    }, headers=h)
    assert r.status_code == 200
    state = r.json()["state"]

    class BoomFlow:
        def fetch_token(self, **kwargs):
            raise Warning('Scope has changed from "a" to "b".')

    monkeypatch.setattr("cockpit.api.mailboxes._google_flow", lambda **kwargs: BoomFlow())
    r = client.get(
        "/api/mailboxes/connect/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error=scope_mismatch" in r.headers["location"]


def test_mailboxes_connect_callback_saves_mailbox_and_relaxes_scope(auth_client, monkeypatch):
    import os
    from engine.adapters.google_scopes import USERINFO_PROFILE

    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-secret",
        "redirect_uri": "http://127.0.0.1:8765/api/mailboxes/connect/callback",
    }, headers=h)
    assert r.status_code == 200
    state = r.json()["state"]
    seen = {}

    class FakeCreds:
        token = "access-token"
        scopes = ["https://www.googleapis.com/auth/gmail.send", USERINFO_PROFILE]

        def to_authorized_user_info(self):
            return {"token": "access-token", "refresh_token": "refresh", "scopes": self.scopes}

    class FakeFlow:
        credentials = FakeCreds()

        def fetch_token(self, code=None, **kwargs):
            seen["code"] = code
            seen["relaxed"] = os.environ.get("OAUTHLIB_RELAX_TOKEN_SCOPE")
            seen["redirect_uri"] = self.redirect_uri

    def fake_google_flow(**kwargs):
        flow = FakeFlow()
        flow.redirect_uri = kwargs["redirect_uri"]
        seen["flow_redirect_uri"] = kwargs["redirect_uri"]
        return flow

    monkeypatch.setattr("cockpit.api.mailboxes._google_flow", fake_google_flow)
    monkeypatch.setattr("cockpit.api.mailboxes._discover_email", lambda creds: "me@gmail.com")
    r = client.get(
        "/api/mailboxes/connect/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert "connected=1" in (r.headers.get("location") or "")
    assert seen["code"] == "auth-code"
    assert seen["relaxed"] == "1"
    assert seen["flow_redirect_uri"].endswith("/api/mailboxes/connect/callback")
    boxes = client.get("/api/mailboxes", headers=h).json()
    assert len(boxes) == 1
    assert boxes[0]["email_address"] == "me@gmail.com"


def test_oauth_state_roundtrip_does_not_need_session(monkeypatch):
    from cockpit.api.mailboxes import decode_mailbox_oauth_state, encode_mailbox_oauth_state

    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "env-secret")
    state = encode_mailbox_oauth_state({
        "client_id": "cid.apps.googleusercontent.com",
        "client_secret": "env-secret",
        "redirect_uri": "https://example.test/api/mailboxes/connect/callback",
        "tenant_id": "t1",
        "user_id": "u1",
    })
    decoded = decode_mailbox_oauth_state(state)
    assert decoded is not None
    assert decoded["client_id"] == "cid.apps.googleusercontent.com"
    assert decoded["client_secret"] == "env-secret"
    assert decoded["tenant_id"] == "t1"
    assert decoded["user_id"] == "u1"


def test_connect_callback_reads_self_contained_state_without_session(auth_client, monkeypatch):
    from engine.adapters.google_scopes import USERINFO_PROFILE

    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-secret",
        "redirect_uri": "http://127.0.0.1:8765/api/mailboxes/connect/callback",
    }, headers=h)
    assert r.status_code == 200
    state = r.json()["state"]

    class FakeCreds:
        token = "access-token"
        refresh_token = "refresh"
        scopes = ["https://www.googleapis.com/auth/gmail.send", USERINFO_PROFILE]

        def to_authorized_user_info(self):
            raise ValueError("Authorized user info was not in the expected format, missing fields refresh_token.")

    class FakeFlow:
        credentials = FakeCreds()
        redirect_uri = None

        def fetch_token(self, code=None, **kwargs):
            return None

    def fake_google_flow(**kwargs):
        flow = FakeFlow()
        flow.redirect_uri = kwargs["redirect_uri"]
        return flow

    monkeypatch.setattr("cockpit.api.mailboxes._google_flow", fake_google_flow)
    monkeypatch.setattr("cockpit.api.mailboxes._discover_email", lambda creds: "me@gmail.com")
    bare = TestClient(client.app, raise_server_exceptions=True)
    r = bare.get(
        "/api/mailboxes/connect/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    location = r.headers.get("location") or ""
    assert "invalid_or_expired_state" not in location
    assert "connected=1" in location
    boxes = client.get("/api/mailboxes", headers=h).json()
    assert len(boxes) == 1
    assert boxes[0]["has_refresh_token"] is True
    assert boxes[0]["has_access_token"] is True


def test_authorized_user_info_survives_google_dump_raise():
    from engine.adapters.gmail_token_store import authorized_user_info_from_credentials

    class Creds:
        token = "access-now"
        refresh_token = None
        scopes = ["https://www.googleapis.com/auth/gmail.send"]
        client_id = "cid"
        client_secret = "csec"
        token_uri = "https://oauth2.googleapis.com/token"

        def to_authorized_user_info(self):
            raise ValueError("missing fields refresh_token")

    info = authorized_user_info_from_credentials(Creds())
    assert info["token"] == "access-now"
    assert not info.get("refresh_token")


def test_connect_start_requests_offline_consent(auth_client):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-secret",
    }, headers=h)
    assert r.status_code == 200
    url = r.json()["authorization_url"]
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "include_granted_scopes" not in url


def test_authorized_user_info_keeps_refresh_when_google_omits_it():
    from engine.adapters.gmail_token_store import authorized_user_info_from_credentials

    class Creds:
        token = "access-now"
        refresh_token = "keep-me"
        scopes = ["https://www.googleapis.com/auth/gmail.send"]
        client_id = "cid"
        client_secret = "csec"
        token_uri = "https://oauth2.googleapis.com/token"

        def to_authorized_user_info(self):
            return {"token": "access-now", "scopes": self.scopes}

    info = authorized_user_info_from_credentials(Creds())
    assert info["refresh_token"] == "keep-me"
    assert info["token"] == "access-now"


def test_merge_keeps_existing_refresh_token_on_reconsent():
    from engine.adapters.gmail_token_store import merge_gmail_token_payload

    merged = merge_gmail_token_payload(
        {"token": "new-access", "scopes": ["s"]},
        {"token": "old-access", "refresh_token": "old-refresh"},
    )
    assert merged["refresh_token"] == "old-refresh"
    assert merged["token"] == "new-access"


def test_db_token_store_scopes_only_sets_last_error(storage):
    store, _, _ = storage
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(
        id="m", tenant_id="t", email_address="x@y.com",
        credentials_json={"scopes": ["https://www.googleapis.com/auth/gmail.send"]},
        created_at=now, updated_at=now,
    ))
    ts = DbTokenStore(store=store, mailbox_id="m")
    with pytest.raises(TokenInvalid) as exc:
        ts.load()
    assert "refresh_token" in str(exc.value)
    mb = store.get_mailbox("m")
    assert mb.status == "active"
    assert mb.last_error
    assert "refresh_token" in mb.last_error


def test_mailboxes_connect_callback_upserts_and_keeps_refresh(auth_client, monkeypatch):
    from engine.adapters.google_scopes import USERINFO_PROFILE

    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = client.get("/api/auth/me", headers=h).json()
    now = datetime.now(timezone.utc)
    client.app.state.store.save_mailbox(Mailbox(
        id="mbx_keep",
        tenant_id=me["tenant_id"],
        email_address="me@gmail.com",
        credentials_json={"token": "old", "refresh_token": "keep-refresh"},
        created_at=now, updated_at=now,
    ))
    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-secret",
        "redirect_uri": "http://127.0.0.1:8765/api/mailboxes/connect/callback",
    }, headers=h)
    assert r.status_code == 200
    state = r.json()["state"]

    class FakeCreds:
        token = "new-access"
        refresh_token = None
        scopes = ["https://www.googleapis.com/auth/gmail.send", USERINFO_PROFILE]

        def to_authorized_user_info(self):
            return {"token": "new-access", "scopes": self.scopes}

    class FakeFlow:
        credentials = FakeCreds()
        redirect_uri = None

        def fetch_token(self, code=None, **kwargs):
            return None

    def fake_google_flow(**kwargs):
        flow = FakeFlow()
        flow.redirect_uri = kwargs["redirect_uri"]
        return flow

    monkeypatch.setattr("cockpit.api.mailboxes._google_flow", fake_google_flow)
    monkeypatch.setattr("cockpit.api.mailboxes._discover_email", lambda creds: "me@gmail.com")
    r = client.get(
        "/api/mailboxes/connect/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert "connected=1" in (r.headers.get("location") or "")
    saved = client.app.state.store.get_mailbox("mbx_keep")
    assert saved.email_address == "me@gmail.com"
    assert saved.credentials_json["refresh_token"] == "keep-refresh"
    assert saved.credentials_json["token"] == "new-access"
    assert saved.status == "active"
    assert saved.last_error is None
    boxes = client.get("/api/mailboxes", headers=h).json()
    assert len(boxes) == 1


def test_mailboxes_connect_callback_rejects_unusable_token(auth_client, monkeypatch):
    client, tokens = auth_client
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/api/mailboxes/connect/start", json={
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-secret",
        "redirect_uri": "http://127.0.0.1:8765/api/mailboxes/connect/callback",
    }, headers=h)
    state = r.json()["state"]

    class FakeCreds:
        token = None
        refresh_token = None
        scopes = ["https://www.googleapis.com/auth/gmail.send"]

        def to_authorized_user_info(self):
            return {"scopes": self.scopes}

    class FakeFlow:
        credentials = FakeCreds()
        redirect_uri = None

        def fetch_token(self, code=None, **kwargs):
            return None

    def fake_google_flow(**kwargs):
        flow = FakeFlow()
        flow.redirect_uri = kwargs["redirect_uri"]
        return flow

    monkeypatch.setattr("cockpit.api.mailboxes._google_flow", fake_google_flow)
    monkeypatch.setattr("cockpit.api.mailboxes._discover_email", lambda creds: "me@gmail.com")
    r = client.get(
        "/api/mailboxes/connect/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "missing_refresh_token" in r.headers["location"]
    assert client.get("/api/mailboxes", headers=h).json() == []

