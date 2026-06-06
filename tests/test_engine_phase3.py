"""
Phase 3 tests — RealGmailSendAdapter, GmailTokenStore, dry-run, error handling.

Strategy
--------
We test the production Gmail adapter against a fake gmail client + a fake
token store. Same shape as Phase 1, but exercising the new behaviors:
    * dry-run path
    * 429 rate-limit -> retryable + Retry-After honored
    * 401 / 403 / invalid_grant -> non-retryable + token marked invalid
    * thread_id passed through
    * MIME multipart/alternative with body_html
    * token store loads + saves on success + persists invalid sentinel
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine import (
    AdapterRegistry,
    EngineRuntime,
    JsonFileTokenStore,
    OutboundAgentV1,
    RealGmailSendAdapter,
    TokenInvalid,
    TokenUnavailable,
    open_storage,
    JobState,
)
from engine.adapters import gmail_token_store as token_store_mod


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures and fakes
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path/'p3.db'}")


class _FakeCreds:
    """Stand-in for google.oauth2.credentials.Credentials."""

    def __init__(self, *, token="tok", refresh_token="rt", scopes=("gmail.send",)):
        self.token = token
        self.refresh_token = refresh_token
        self.scopes = list(scopes)
        self.client_id = "cid"
        self.client_secret = "csec"
        self.token_uri = "https://oauth2.googleapis.com/token"
        self.expired = False
        self.expiry = None

    def refresh(self, _request):
        self.expired = False
        self.token = "tok_refreshed"

    def to_authorized_user_info(self):
        return {
            "token": self.token,
            "refresh_token": self.refresh_token,
            "token_uri": self.token_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scopes": list(self.scopes),
        }


class _FakeStore:
    """In-memory GmailTokenStore for tests."""

    def __init__(self, *, creds=None, raise_on_load=None):
        self._creds = creds
        self._raise = raise_on_load
        self.saved = []
        self.invalid_reason = None

    def load(self):
        if self._raise is not None:
            raise self._raise
        if self._creds is None:
            raise TokenUnavailable("no creds configured")
        return self._creds

    def save(self, c):
        self.saved.append(c)

    def mark_invalid(self, reason: str):
        self.invalid_reason = reason

    def is_invalid(self) -> bool:
        return self.invalid_reason is not None


class _FakeHttpResp:
    def __init__(self, status, headers=None):
        self.status = status
        self._headers = dict(headers or {})


class _HttpError(Exception):
    """Mimics googleapiclient.errors.HttpError just enough for classifier."""

    def __init__(self, status, message, headers=None):
        super().__init__(f"<HttpError {status} when requesting ... \"{message}\">")
        self.resp = _FakeHttpResp(status, headers)


class _FakeGmailClient:
    """Fake Gmail client. Configurable behavior per test."""

    def __init__(self, *, message_id="msg_1", thread_id="thread_1", raise_on_send=None):
        self._message_id = message_id
        self._thread_id = thread_id
        self._raise = raise_on_send
        self.sent_payloads: list[dict] = []

    def users(self):
        return self

    def messages(self):
        return self

    def send(self, *, userId, body):
        self.sent_payloads.append({"userId": userId, "body": body})
        return self

    def execute(self):
        if self._raise is not None:
            raise self._raise
        return {"id": self._message_id, "threadId": self._thread_id}


# ─────────────────────────────────────────────────────────────────────────────
# Token store: JSON file roundtrip
# ─────────────────────────────────────────────────────────────────────────────


def test_json_token_store_load_when_missing_raises_unavailable(tmp_path):
    store = JsonFileTokenStore(token_path=str(tmp_path / "no.json"))
    with pytest.raises(TokenUnavailable):
        store.load()


def test_json_token_store_persists_and_clears_invalid_sentinel(tmp_path):
    store = JsonFileTokenStore(token_path=str(tmp_path / "tok.json"))
    assert store.is_invalid() is False
    store.mark_invalid("test reason")
    assert store.is_invalid() is True
    sidecar = (tmp_path / "tok.json.invalid.json")
    payload = json.loads(sidecar.read_text())
    assert payload["invalid"] is True
    assert "test reason" in payload["reason"]
    store.clear_invalid()
    assert store.is_invalid() is False


def test_json_token_store_load_marked_invalid_raises(tmp_path):
    path = tmp_path / "tok.json"
    # Write a vaguely-valid token then mark it invalid.
    path.write_text(json.dumps({
        "token": "tok", "refresh_token": "rt",
        "client_id": "cid", "client_secret": "csec",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/gmail.send"],
    }))
    store = JsonFileTokenStore(token_path=str(path))
    store.mark_invalid("forced")
    with pytest.raises(TokenInvalid):
        store.load()


def test_json_token_store_save_writes_atomic(tmp_path):
    store = JsonFileTokenStore(token_path=str(tmp_path / "tok.json"))
    store.save(_FakeCreds(token="abc", refresh_token="def"))
    on_disk = json.loads((tmp_path / "tok.json").read_text())
    assert on_disk["token"] == "abc"
    assert on_disk["refresh_token"] == "def"


# ─────────────────────────────────────────────────────────────────────────────
# Adapter — happy path, dry run, thread reply
# ─────────────────────────────────────────────────────────────────────────────


def _seed_engagement(store, *, hitl_threshold=0, prospects=1, with_html=False, with_thread=False):
    from engine import Engagement, Agent, Prospect

    eng = Engagement(
        id="eng_real", customer_name="Real", offer="Real offer",
        icp_description="ICP",
        price_per_outcome_cents=50_000, monthly_budget_cents=100_000,
    )
    store.save_engagement(eng)
    cfg = {
        "hitl_threshold": hitl_threshold,
        "send_gap_seconds": 0,
        "subject_template": "Hi {to_name}",
        "body_template": "Hi {to_name},\n\nOffer: {offer}\n",
    }
    agent = Agent(id="agent_real", engagement_id=eng.id, runner_kind=OutboundAgentV1.runner_kind, config=cfg)
    store.save_agent(agent)
    for i in range(prospects):
        store.save_prospect(Prospect(
            id=f"p_{i}", engagement_id=eng.id,
            email=f"p{i}@example.com", full_name=f"Person {i}",
            company=f"Co {i}",
        ))
    return eng, agent


def test_real_adapter_happy_path_via_runtime(storage):
    store, events, ledger = storage
    fake = _FakeGmailClient()
    tokens = _FakeStore(creds=_FakeCreds())
    adapter = RealGmailSendAdapter(
        sender_email="me@example.com",
        token_store=tokens,
        gmail_build=lambda creds: fake,
        dry_run=False,
    )
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, prospects=1)
    rt.run_once()
    assert len(fake.sent_payloads) == 1
    assert "raw" in fake.sent_payloads[0]["body"]
    succeeded = list(store.list_jobs_by_state(JobState.SUCCEEDED.value))
    assert len(succeeded) == 1
    assert succeeded[0].result.get("gmail_message_id") == "msg_1"
    assert succeeded[0].result.get("dry_run") is False
    assert ledger.total_spent_cents("eng_real", category="email_send") == 1
    # Token was saved (refresh-on-success path).
    assert len(tokens.saved) == 1


def test_real_adapter_dry_run_runs_full_path_without_sending(storage):
    store, events, ledger = storage
    fake = _FakeGmailClient()
    tokens = _FakeStore(creds=_FakeCreds())
    adapter = RealGmailSendAdapter(
        sender_email="me@example.com",
        token_store=tokens,
        gmail_build=lambda creds: fake,
        dry_run=True,
    )
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, prospects=1)
    rt.run_once()
    # Network call NOT made.
    assert fake.sent_payloads == []
    succeeded = list(store.list_jobs_by_state(JobState.SUCCEEDED.value))
    assert len(succeeded) == 1
    assert succeeded[0].result.get("dry_run") is True
    assert succeeded[0].result.get("sent") is False
    # Cost ledger is NOT debited in dry-run.
    assert ledger.total_spent_cents("eng_real", category="email_send") == 0
    # Dry-run event was emitted.
    kinds = [e.kind.value for e in events.list_recent(engagement_id="eng_real", limit=20)]
    assert "email.dry_run" in kinds
    assert "email.sent" not in kinds


def test_real_adapter_thread_id_is_passed_to_gmail(storage):
    store, events, ledger = storage
    fake = _FakeGmailClient()
    adapter = RealGmailSendAdapter(
        sender_email="me@example.com",
        token_store=_FakeStore(creds=_FakeCreds()),
        gmail_build=lambda creds: fake,
        dry_run=False,
    )
    # Construct one Job manually so we can pass a thread_id.
    from engine import Engagement, Agent, Prospect, Job, JobKind
    store.save_engagement(Engagement(id="e", customer_name="C", offer="O", icp_description="I"))
    store.save_agent(Agent(id="a", engagement_id="e", runner_kind="outbound.v1"))
    store.save_prospect(Prospect(id="p", engagement_id="e", email="x@y.com"))
    store.save_job(Job(
        id="j_thread", engagement_id="e", agent_id="a",
        kind=JobKind.EMAIL_SEND,
        payload={
            "to_email": "x@y.com",
            "subject": "Re: hi",
            "body_text": "thanks",
            "thread_id": "thread_42",
            "in_reply_to": "<msg-original@mail.gmail.com>",
        },
        prospect_id="p",
    ))
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    rt.execute_due_jobs()
    body = fake.sent_payloads[0]["body"]
    assert body.get("threadId") == "thread_42"
    # MIME contains the In-Reply-To header.
    import base64, email
    decoded = base64.urlsafe_b64decode(body["raw"]).decode()
    msg = email.message_from_string(decoded)
    assert msg["In-Reply-To"] == "<msg-original@mail.gmail.com>"
    assert msg["References"] == "<msg-original@mail.gmail.com>"


def test_real_adapter_multipart_alternative_with_body_html(storage):
    store, events, ledger = storage
    fake = _FakeGmailClient()
    adapter = RealGmailSendAdapter(
        sender_email="me@example.com",
        token_store=_FakeStore(creds=_FakeCreds()),
        gmail_build=lambda creds: fake,
        dry_run=False,
    )
    from engine import Engagement, Agent, Prospect, Job, JobKind
    store.save_engagement(Engagement(id="e", customer_name="C", offer="O", icp_description="I"))
    store.save_agent(Agent(id="a", engagement_id="e", runner_kind="outbound.v1"))
    store.save_prospect(Prospect(id="p", engagement_id="e", email="x@y.com"))
    store.save_job(Job(
        id="j_html", engagement_id="e", agent_id="a",
        kind=JobKind.EMAIL_SEND,
        payload={
            "to_email": "x@y.com",
            "subject": "Hi",
            "body_text": "plain version",
            "body_html": "<p>html version</p>",
        },
        prospect_id="p",
    ))
    EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    ).execute_due_jobs()
    import base64, email
    decoded = base64.urlsafe_b64decode(fake.sent_payloads[0]["body"]["raw"]).decode()
    msg = email.message_from_string(decoded)
    assert msg.get_content_type().startswith("multipart/alternative")
    parts = list(msg.walk())
    text_parts = [p.get_payload(decode=True).decode() for p in parts if p.get_content_type() == "text/plain"]
    html_parts = [p.get_payload(decode=True).decode() for p in parts if p.get_content_type() == "text/html"]
    assert any("plain version" in t for t in text_parts)
    assert any("<p>html version</p>" in h for h in html_parts)


# ─────────────────────────────────────────────────────────────────────────────
# Adapter — error classification
# ─────────────────────────────────────────────────────────────────────────────


def test_real_adapter_429_is_retryable_and_honors_retry_after(storage):
    store, events, ledger = storage
    fake = _FakeGmailClient(raise_on_send=_HttpError(429, "rateLimitExceeded", headers={"Retry-After": "120"}))
    tokens = _FakeStore(creds=_FakeCreds())
    adapter = RealGmailSendAdapter(
        sender_email="me@example.com",
        token_store=tokens,
        gmail_build=lambda creds: fake,
        dry_run=False,
    )
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, prospects=1)
    rt.run_once()
    # Job should be retry-scheduled (NOT dead-lettered).
    pending = list(store.list_jobs_by_state(JobState.PENDING.value, engagement_id="eng_real"))
    dead = list(store.list_jobs_by_state(JobState.DEAD_LETTERED.value, engagement_id="eng_real"))
    assert len(pending) == 1
    assert len(dead) == 0
    job = pending[0]
    # The adapter set not_before to (now + 120s) — runtime won't pick it up yet.
    assert job.not_before is not None
    assert job.not_before > datetime.now(timezone.utc) + timedelta(seconds=60)
    # Token was NOT marked invalid.
    assert tokens.invalid_reason is None
    # Rate-limited event was emitted.
    kinds = [e.kind.value for e in events.list_recent(engagement_id="eng_real", limit=20)]
    assert "email.rate_limited" in kinds


def test_real_adapter_401_marks_token_invalid_and_dead_letters(storage):
    store, events, ledger = storage
    fake = _FakeGmailClient(raise_on_send=_HttpError(401, "Invalid Credentials"))
    tokens = _FakeStore(creds=_FakeCreds())
    adapter = RealGmailSendAdapter(
        sender_email="me@example.com",
        token_store=tokens,
        gmail_build=lambda creds: fake,
        dry_run=False,
    )
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, prospects=1)
    rt.run_once()
    dead = list(store.list_jobs_by_state(JobState.DEAD_LETTERED.value, engagement_id="eng_real"))
    assert len(dead) == 1
    assert dead[0].attempt == 1  # non-retryable
    # Token was marked invalid via the store.
    assert tokens.invalid_reason is not None
    # Event was emitted.
    kinds = [e.kind.value for e in events.list_recent(engagement_id="eng_real", limit=20)]
    assert "gmail.token_invalid" in kinds


def test_real_adapter_invalid_grant_in_repr_is_token_invalid(storage):
    store, events, ledger = storage
    fake = _FakeGmailClient(raise_on_send=Exception("invalid_grant: Token has been expired or revoked."))
    tokens = _FakeStore(creds=_FakeCreds())
    adapter = RealGmailSendAdapter(
        sender_email="me@example.com",
        token_store=tokens,
        gmail_build=lambda creds: fake,
        dry_run=False,
    )
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, prospects=1)
    rt.run_once()
    dead = list(store.list_jobs_by_state(JobState.DEAD_LETTERED.value, engagement_id="eng_real"))
    assert len(dead) == 1
    assert tokens.invalid_reason is not None


def test_real_adapter_500_is_retryable(storage):
    store, events, ledger = storage
    fake = _FakeGmailClient(raise_on_send=_HttpError(503, "Service Unavailable"))
    adapter = RealGmailSendAdapter(
        sender_email="me@example.com",
        token_store=_FakeStore(creds=_FakeCreds()),
        gmail_build=lambda creds: fake,
        dry_run=False,
    )
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, prospects=1)
    rt.run_once()
    # Job is retry-scheduled (lives in pending now, attempt=1)
    pending = list(store.list_jobs_by_state(JobState.PENDING.value, engagement_id="eng_real"))
    assert len(pending) == 1
    assert pending[0].attempt == 1


def test_real_adapter_400_bad_recipient_is_non_retryable(storage):
    store, events, ledger = storage
    fake = _FakeGmailClient(raise_on_send=_HttpError(400, "Recipient address rejected"))
    adapter = RealGmailSendAdapter(
        sender_email="me@example.com",
        token_store=_FakeStore(creds=_FakeCreds()),
        gmail_build=lambda creds: fake,
        dry_run=False,
    )
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, prospects=1)
    rt.run_once()
    dead = list(store.list_jobs_by_state(JobState.DEAD_LETTERED.value, engagement_id="eng_real"))
    assert len(dead) == 1
    assert dead[0].attempt == 1


# ─────────────────────────────────────────────────────────────────────────────
# Adapter — token store integration
# ─────────────────────────────────────────────────────────────────────────────


def test_real_adapter_with_unavailable_token_fails_non_retryable(storage):
    store, events, ledger = storage
    tokens = _FakeStore(raise_on_load=TokenUnavailable("no token"))
    adapter = RealGmailSendAdapter(
        sender_email="me@example.com",
        token_store=tokens,
        gmail_build=lambda creds: _FakeGmailClient(),
        dry_run=False,
    )
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, prospects=1)
    rt.run_once()
    dead = list(store.list_jobs_by_state(JobState.DEAD_LETTERED.value, engagement_id="eng_real"))
    assert len(dead) == 1
    assert dead[0].attempt == 1


def test_real_adapter_with_invalid_token_emits_event(storage):
    store, events, ledger = storage
    tokens = _FakeStore(raise_on_load=TokenInvalid("operator must reconnect"))
    adapter = RealGmailSendAdapter(
        sender_email="me@example.com",
        token_store=tokens,
        gmail_build=lambda creds: _FakeGmailClient(),
        dry_run=False,
    )
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, prospects=1)
    rt.run_once()
    kinds = [e.kind.value for e in events.list_recent(engagement_id="eng_real", limit=20)]
    assert "gmail.token_invalid" in kinds


# ─────────────────────────────────────────────────────────────────────────────
# Cockpit — adapter wiring + UI banner
# ─────────────────────────────────────────────────────────────────────────────


def test_cockpit_uses_console_adapter_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTOREACH_GMAIL_TOKEN_PATH", raising=False)
    monkeypatch.delenv("AUTOREACH_GMAIL_SENDER", raising=False)
    monkeypatch.delenv("AUTOREACH_GMAIL_DRY_RUN", raising=False)
    from cockpit import create_app
    from fastapi.testclient import TestClient

    app = create_app(db_url=f"sqlite:///{tmp_path/'cock.db'}")
    client = TestClient(app)
    health = client.get("/healthz").json()
    assert health["email_adapter"]["kind"] == "console"
    # Topbar shows the dev banner.
    page = client.get("/engagements").text
    assert "Console adapter (dev)" in page


def test_cockpit_uses_gmail_adapter_when_configured(tmp_path, monkeypatch):
    token_path = tmp_path / "tok.json"
    token_path.write_text(json.dumps({
        "token": "tok", "refresh_token": "rt",
        "client_id": "cid", "client_secret": "csec",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/gmail.send"],
    }))
    monkeypatch.setenv("AUTOREACH_GMAIL_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("AUTOREACH_GMAIL_SENDER", "ops@example.com")
    monkeypatch.setenv("AUTOREACH_GMAIL_DRY_RUN", "1")  # dry-run so it's safe even if misconfigured

    from cockpit import create_app
    from fastapi.testclient import TestClient

    app = create_app(db_url=f"sqlite:///{tmp_path/'cock.db'}")
    client = TestClient(app)
    health = client.get("/healthz").json()
    assert health["email_adapter"]["kind"] == "gmail"
    assert health["email_adapter"]["sender"] == "ops@example.com"
    assert health["email_adapter"]["dry_run"] is True
    page = client.get("/engagements").text
    assert "Gmail · DRY-RUN" in page


def test_cockpit_shows_invalid_banner_when_token_marked_invalid(tmp_path, monkeypatch):
    token_path = tmp_path / "tok.json"
    token_path.write_text(json.dumps({
        "token": "tok", "refresh_token": "rt",
        "client_id": "cid", "client_secret": "csec",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/gmail.send"],
    }))
    sidecar = token_path.with_suffix(token_path.suffix + ".invalid.json")
    sidecar.write_text(json.dumps({"invalid": True, "reason": "test", "marked_at": "now"}))
    monkeypatch.setenv("AUTOREACH_GMAIL_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("AUTOREACH_GMAIL_SENDER", "ops@example.com")
    monkeypatch.delenv("AUTOREACH_GMAIL_DRY_RUN", raising=False)

    from cockpit import create_app
    from fastapi.testclient import TestClient

    app = create_app(db_url=f"sqlite:///{tmp_path/'cock.db'}")
    client = TestClient(app)
    health = client.get("/healthz").json()
    assert health["email_adapter"]["token_invalid"] is True
    page = client.get("/engagements").text
    assert "Gmail token invalid" in page
