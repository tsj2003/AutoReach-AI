"""
Phase 3 step 3 — reply classifier + GmailReplyDetector + cockpit poll button.

We don't hit the live Gemini API here. Instead we exercise:
    * GeminiClient: configuration error path (no API key)
    * classify_and_draft: graceful fallback on Gemini failures
    * GmailReplyDetector: end-to-end via a fake gmail client + injected fake
      Gemini client. Idempotent. Auto-responder defers, doesn't record.
    * Cockpit: poll-replies button is gated, posts work, summary banner renders.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest

from engine import (
    AdapterRegistry,
    EngineRuntime,
    JsonFileTokenStore,
    OutboundAgentV1,
    RealGmailSendAdapter,
    open_storage,
    JobState,
)
from engine.llm import (
    GeminiClient,
    GeminiError,
    GeminiResult,
    GeminiUnavailable,
    estimate_cost_cents,
)
from engine.llm.classifier import classify_and_draft
from engine.services import GmailReplyDetector, OperationsService
from engine.services.reply_detector import TenantMailboxReplyDetector
from engine.auth.mailbox_models import Mailbox


# ─────────────────────────────────────────────────────────────────────────────
# Test doubles
# ─────────────────────────────────────────────────────────────────────────────


class _FakeGeminiClient:
    """Drop-in replacement for GeminiClient with scripted responses."""

    def __init__(self, scripted_response: dict | Exception):
        self._scripted = scripted_response

    def generate_json(self, *, prompt: str, **_kwargs):
        if isinstance(self._scripted, Exception):
            raise self._scripted
        return GeminiResult(
            data=dict(self._scripted),
            raw_text=json.dumps(self._scripted),
            model="fake-model",
        )


class _FakeGmailThread:
    """Mimics the response shape of gmail.users().threads().get(...)."""

    def __init__(self, messages: list[dict]):
        self._messages = messages

    def execute(self) -> dict:
        return {"messages": self._messages}


class _FakeGmailClient:
    """Tiny fake of the googleapiclient Gmail client used by the detector."""

    def __init__(self, *, threads: dict[str, list[dict]] | None = None):
        # threads is a map: thread_id -> list of gmail message dicts
        self._threads = threads or {}
        self._last_thread_get_id: Optional[str] = None

    def users(self):
        return self

    def threads(self):
        return self

    def get(self, *, userId, id, format, metadataHeaders):
        self._last_thread_get_id = id
        msgs = self._threads.get(id, [])
        return _FakeGmailThread(msgs)


def _gmail_msg(*, msg_id: str, from_addr: str, subject: str, snippet: str) -> dict:
    return {
        "id": msg_id,
        "snippet": snippet,
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "Subject", "value": subject},
            ]
        },
    }


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path/'p3r.db'}")


@pytest.fixture
def ops_kit(storage):
    store, events, ledger = storage
    ops = OperationsService(store=store, events=events)
    return store, events, ledger, ops


# ─────────────────────────────────────────────────────────────────────────────
# GeminiClient
# ─────────────────────────────────────────────────────────────────────────────


def test_gemini_client_without_key_raises_unavailable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = GeminiClient(api_key="")
    with pytest.raises(GeminiUnavailable):
        client.generate_json(prompt="hello")


def test_estimate_cost_is_at_least_one_cent():
    assert estimate_cost_cents(prompt_chars=10, output_chars=10) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# classify_and_draft
# ─────────────────────────────────────────────────────────────────────────────


def test_classify_and_draft_happy_interested():
    fake = _FakeGeminiClient({
        "classification": "interested",
        "suggested_reply": "Happy to chat — book here: https://cal.com/x",
    })
    out = classify_and_draft(
        snippet="Sounds interesting, send me a calendar link",
        original_subject="quick question",
        booking_url="https://cal.com/x",
        client=fake,
    )
    assert out.classification == "interested"
    assert "cal.com/x" in out.suggested_reply
    assert out.fallback_used is False
    assert out.error is None
    assert out.estimated_cost_cents >= 1
    assert out.openinference_trace_id is not None
    assert len(out.openinference_trace_id) == 32


def test_classify_and_draft_auto_clears_suggested():
    fake = _FakeGeminiClient({
        "classification": "auto",
        # The model should leave it blank, but if it doesn't we still must.
        "suggested_reply": "I'm out of office until Monday",
    })
    out = classify_and_draft(snippet="I am OOO until Monday", client=fake)
    assert out.classification == "auto"
    assert out.suggested_reply == ""


def test_classify_and_draft_falls_back_when_gemini_unavailable():
    fake = _FakeGeminiClient(GeminiUnavailable("no api key"))
    out = classify_and_draft(snippet="hi there", client=fake)
    assert out.classification == "objection"
    assert out.suggested_reply == ""
    assert out.fallback_used is True
    assert "no api key" in (out.error or "")


def test_classify_and_draft_falls_back_on_gemini_error():
    fake = _FakeGeminiClient(GeminiError("network down"))
    out = classify_and_draft(snippet="hi there", client=fake)
    assert out.classification == "objection"
    assert out.fallback_used is True


def test_classify_and_draft_rejects_invalid_label():
    fake = _FakeGeminiClient({
        "classification": "definitely-not-a-real-label",
        "suggested_reply": "whatever",
    })
    out = classify_and_draft(snippet="hi", client=fake)
    assert out.classification == "objection"
    assert out.fallback_used is True
    assert "invalid classification" in (out.error or "")


def test_classify_and_draft_empty_snippet_short_circuits():
    out = classify_and_draft(snippet="   ")
    assert out.classification == "objection"
    assert out.fallback_used is True
    assert out.estimated_cost_cents == 0


# ─────────────────────────────────────────────────────────────────────────────
# GmailReplyDetector — end-to-end via fakes
# ─────────────────────────────────────────────────────────────────────────────


def _seed_with_sent_email(store, events, ledger, *, thread_id="thread_1", tenant_id=None, mailbox_id=None):
    """
    Seed an Engagement with one prospect we already 'sent' to. The detector
    finds the sent thread by reading the EMAIL_SENT event log.
    """
    from engine import (
        Agent, Engagement, Event, EventKind, Prospect,
    )

    eng = Engagement(
        id="eng_r", customer_name="Replies", offer="Offer",
        icp_description="ICP",
        booking_url="https://cal.com/me",
        price_per_outcome_cents=50_000,
    )
    store.save_engagement(eng, tenant_id=tenant_id)
    store.save_agent(Agent(id="a_r", engagement_id=eng.id, runner_kind=OutboundAgentV1.runner_kind))
    prospect = Prospect(
        id="p_r", engagement_id=eng.id,
        email="ceo@target.com", full_name="Target CEO",
        company="Target Co",
        status="contacted",
    )
    store.save_prospect(prospect)
    events.emit(Event(
        id="ev_sent", kind=EventKind.EMAIL_SENT,
        engagement_id=eng.id, agent_id="a_r",
        job_id="j_sent", prospect_id=prospect.id,
        payload={
            "to": "ceo@target.com",
            "via": "gmail",
            "gmail_message_id": "msg_outbound_1",
            "gmail_thread_id": thread_id,
            **({"mailbox_id": mailbox_id} if mailbox_id else {}),
        },
    ))
    return eng, prospect


def test_detector_records_one_real_reply_and_drafts(ops_kit, tmp_path):
    store, events, ledger, ops = ops_kit
    eng, prospect = _seed_with_sent_email(store, events, ledger)

    fake_gmail = _FakeGmailClient(threads={
        "thread_1": [
            _gmail_msg(msg_id="msg_outbound_1", from_addr="me@example.com",
                       subject="quick question", snippet="hi, here's our offer"),
            _gmail_msg(msg_id="msg_inbound_1", from_addr="ceo@target.com",
                       subject="Re: quick question",
                       snippet="Sounds interesting, send a calendar link."),
        ],
    })
    fake_gemini = _FakeGeminiClient({
        "classification": "interested",
        "suggested_reply": "Great — book a 15-min slot here: https://cal.com/me",
    })
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({
        "token": "tok", "refresh_token": "rt", "client_id": "c", "client_secret": "s",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    }))
    # Patch the Credentials lazy-import to avoid the real google-auth flow.
    detector = GmailReplyDetector(
        store=store, events=events, ledger=ledger, ops=ops,
        token_store=_FakeTokenStore(),
        sender_email="me@example.com",
        gemini=fake_gemini,
        gmail_build=lambda creds: fake_gmail,
    )
    result = detector.poll(eng.id)

    assert result.replies_recorded == 1
    assert result.duplicates_skipped == 0
    assert result.auto_responders == 0
    assert result.fell_back_to_default == 0
    assert result.token_invalid is False

    # Reply was persisted and linked to prospect.
    replies = list(ops.list_replies(eng.id, status="pending"))
    assert len(replies) == 1
    r = replies[0]
    assert r.classification == "interested"
    assert r.external_message_id == "msg_inbound_1"
    assert "cal.com/me" in r.suggested_reply
    assert r.prospect_id == prospect.id

    # Prospect was advanced to status='replied'.
    assert store.get_prospect(prospect.id).status == "replied"

    # LLM cost was debited.
    assert ledger.total_spent_cents(eng.id, category="llm") >= 1

    from engine import EventKind
    classified_events = list(
        events.list_recent(
            engagement_id=eng.id,
            kind=EventKind.REPLY_CLASSIFIED.value,
            limit=10,
        )
    )
    assert len(classified_events) == 1
    trace_id = classified_events[0].payload["openinference_trace_id"]
    assert trace_id
    assert len(trace_id) == 32
    costs = list(ledger.list_recent(eng.id, limit=10))
    assert any(c.metadata.get("openinference_trace_id") == trace_id for c in costs)


def test_detector_filters_threads_by_mailbox_id(ops_kit):
    store, events, ledger, ops = ops_kit
    eng, prospect = _seed_with_sent_email(
        store,
        events,
        ledger,
        thread_id="thread_wrong",
        mailbox_id="mbx-other",
    )
    from engine import Event, EventKind
    events.emit(Event(
        id="ev_sent_right", kind=EventKind.EMAIL_SENT,
        engagement_id=eng.id, agent_id="a_r",
        job_id="j_sent_right", prospect_id=prospect.id,
        payload={
            "to": "ceo@target.com",
            "via": "gmail",
            "gmail_message_id": "msg_outbound_right",
            "gmail_thread_id": "thread_right",
            "mailbox_id": "mbx-right",
        },
    ))
    fake_gmail = _FakeGmailClient(threads={
        "thread_right": [
            _gmail_msg(msg_id="msg_outbound_right", from_addr="me@example.com", subject="s", snippet=""),
            _gmail_msg(msg_id="msg_inbound_right", from_addr="ceo@target.com", subject="Re: s", snippet="Interested."),
        ],
    })
    detector = GmailReplyDetector(
        store=store, events=events, ledger=ledger, ops=ops,
        token_store=_FakeTokenStore(),
        sender_email="me@example.com",
        gemini=_FakeGeminiClient({"classification": "interested", "suggested_reply": "thanks"}),
        gmail_build=lambda creds: fake_gmail,
        mailbox_id="mbx-right",
    )

    result = detector.poll(eng.id)

    assert result.replies_recorded == 1
    assert fake_gmail._last_thread_get_id == "thread_right"


def test_tenant_mailbox_reply_detector_uses_connected_mailbox(ops_kit, monkeypatch):
    store, events, ledger, ops = ops_kit
    eng, _prospect = _seed_with_sent_email(
        store,
        events,
        ledger,
        thread_id="thread_tenant",
        tenant_id="t-replies",
        mailbox_id="mbx-replies",
    )
    store.save_mailbox(Mailbox(
        id="mbx-replies",
        tenant_id="t-replies",
        email_address="seller@example.com",
        credentials_json={"token": "tok"},
        status="active",
    ))
    fake_gmail = _FakeGmailClient(threads={
        "thread_tenant": [
            _gmail_msg(msg_id="msg_outbound_tenant", from_addr="seller@example.com", subject="s", snippet=""),
            _gmail_msg(msg_id="msg_inbound_tenant", from_addr="ceo@target.com", subject="Re: s", snippet="Interested."),
        ],
    })

    class FakeDbTokenStore:
        def __init__(self, *, store, mailbox_id):
            self.mailbox_id = mailbox_id

        def load(self):
            return object()

    monkeypatch.setattr("engine.services.reply_detector.DbTokenStore", FakeDbTokenStore)
    detector = TenantMailboxReplyDetector(
        store=store,
        events=events,
        ledger=ledger,
        ops=ops,
        gemini=_FakeGeminiClient({"classification": "interested", "suggested_reply": "thanks"}),
        gmail_build_factory=lambda mailbox: (lambda creds: fake_gmail),
    )

    result = detector.poll(eng.id)

    assert result.replies_recorded == 1
    assert result.prospects_scanned == 1
    assert result.errors == []


def test_detector_dedupe_via_external_message_id(ops_kit, tmp_path):
    store, events, ledger, ops = ops_kit
    eng, prospect = _seed_with_sent_email(store, events, ledger)
    fake_gmail = _FakeGmailClient(threads={
        "thread_1": [
            _gmail_msg(msg_id="msg_outbound_1", from_addr="me@example.com", subject="s", snippet=""),
            _gmail_msg(msg_id="msg_inbound_1", from_addr="ceo@target.com",
                       subject="Re: s", snippet="hello, interested"),
        ],
    })
    fake_gemini = _FakeGeminiClient({"classification": "interested", "suggested_reply": "thanks"})
    detector = GmailReplyDetector(
        store=store, events=events, ledger=ledger, ops=ops,
        token_store=_FakeTokenStore(),
        sender_email="me@example.com",
        gemini=fake_gemini,
        gmail_build=lambda creds: fake_gmail,
    )

    first = detector.poll(eng.id)
    second = detector.poll(eng.id)
    third = detector.poll(eng.id)

    assert first.replies_recorded == 1
    assert second.replies_recorded == 0
    assert second.duplicates_skipped == 1
    assert third.duplicates_skipped == 1
    assert len(list(ops.list_replies(eng.id))) == 1


def test_detector_auto_responder_defers_prospect_and_does_not_record(ops_kit, tmp_path):
    store, events, ledger, ops = ops_kit
    eng, prospect = _seed_with_sent_email(store, events, ledger)
    fake_gmail = _FakeGmailClient(threads={
        "thread_1": [
            _gmail_msg(msg_id="msg_out", from_addr="me@example.com", subject="s", snippet=""),
            _gmail_msg(msg_id="msg_ooo", from_addr="ceo@target.com",
                       subject="Auto-reply: Out of office",
                       snippet="I'm out until Monday — automatic reply"),
        ],
    })
    fake_gemini = _FakeGeminiClient({"classification": "auto", "suggested_reply": ""})
    detector = GmailReplyDetector(
        store=store, events=events, ledger=ledger, ops=ops,
        token_store=_FakeTokenStore(),
        sender_email="me@example.com",
        gemini=fake_gemini,
        gmail_build=lambda creds: fake_gmail,
    )
    result = detector.poll(eng.id)
    assert result.auto_responders == 1
    assert result.replies_recorded == 0
    # Prospect status was not changed to 'replied'.
    assert store.get_prospect(prospect.id).status == "contacted"
    # Reply NOT persisted.
    assert list(ops.list_replies(eng.id)) == []


def test_detector_skips_messages_from_us(ops_kit, tmp_path):
    """Replies from the sender themselves (e.g., follow-up they typed manually)
    must not be treated as inbound replies."""
    store, events, ledger, ops = ops_kit
    eng, prospect = _seed_with_sent_email(store, events, ledger)
    fake_gmail = _FakeGmailClient(threads={
        "thread_1": [
            _gmail_msg(msg_id="msg_out_1", from_addr="me@example.com", subject="s", snippet=""),
            _gmail_msg(msg_id="msg_out_2", from_addr="Me Sender <me@example.com>",
                       subject="Re: s", snippet="just bumping this"),
        ],
    })
    detector = GmailReplyDetector(
        store=store, events=events, ledger=ledger, ops=ops,
        token_store=_FakeTokenStore(),
        sender_email="me@example.com",
        gemini=_FakeGeminiClient({"classification": "interested", "suggested_reply": "x"}),
        gmail_build=lambda creds: fake_gmail,
    )
    r = detector.poll(eng.id)
    assert r.replies_recorded == 0
    assert r.threads_polled == 1


def test_detector_token_invalid_returns_gracefully_with_event(ops_kit):
    from engine import TokenInvalid

    store, events, ledger, ops = ops_kit
    eng, _prospect = _seed_with_sent_email(store, events, ledger)
    detector = GmailReplyDetector(
        store=store, events=events, ledger=ledger, ops=ops,
        token_store=_FakeTokenStore(raise_on_load=TokenInvalid("operator must reconnect")),
        sender_email="me@example.com",
        gemini=_FakeGeminiClient({"classification": "interested", "suggested_reply": "x"}),
        gmail_build=lambda creds: _FakeGmailClient(),
    )
    result = detector.poll(eng.id)
    assert result.token_invalid is True
    assert result.replies_recorded == 0
    kinds = [e.kind.value for e in events.list_recent(engagement_id=eng.id, limit=20)]
    assert "gmail.token_invalid" in kinds


def test_detector_falls_back_when_gemini_fails(ops_kit, tmp_path):
    store, events, ledger, ops = ops_kit
    eng, prospect = _seed_with_sent_email(store, events, ledger)
    fake_gmail = _FakeGmailClient(threads={
        "thread_1": [
            _gmail_msg(msg_id="msg_out", from_addr="me@example.com", subject="s", snippet=""),
            _gmail_msg(msg_id="msg_in", from_addr="ceo@target.com",
                       subject="Re: s", snippet="something something"),
        ],
    })
    failing_gemini = _FakeGeminiClient(GeminiError("api went down"))
    detector = GmailReplyDetector(
        store=store, events=events, ledger=ledger, ops=ops,
        token_store=_FakeTokenStore(),
        sender_email="me@example.com",
        gemini=failing_gemini,
        gmail_build=lambda creds: fake_gmail,
    )
    result = detector.poll(eng.id)
    # Reply still recorded — operator can handle manually.
    assert result.replies_recorded == 1
    assert result.fell_back_to_default == 1
    replies = list(ops.list_replies(eng.id))
    assert replies[0].classification == "objection"  # safe default


# ─────────────────────────────────────────────────────────────────────────────
# Cockpit poll-replies button
# ─────────────────────────────────────────────────────────────────────────────


def test_cockpit_poll_button_is_gated_when_gmail_not_configured(tmp_path, monkeypatch):
    """Without Gmail env vars, the poll button should not be shown and the
    POST endpoint returns 400."""
    monkeypatch.delenv("AUTOREACH_GMAIL_TOKEN_PATH", raising=False)
    monkeypatch.delenv("AUTOREACH_GMAIL_SENDER", raising=False)
    monkeypatch.delenv("AUTOREACH_GMAIL_DRY_RUN", raising=False)
    from cockpit import create_app
    from fastapi.testclient import TestClient

    app = create_app(db_url=f"sqlite:///{tmp_path/'cock.db'}")
    client = TestClient(app)
    r = client.post(
        "/engagements",
        data={
            "customer_name": "X", "offer": "O", "icp_description": "I",
            "booking_url": "", "monthly_meeting_target": 0,
            "price_per_outcome_cents": 50000, "monthly_budget_cents": 0,
        },
        follow_redirects=False,
    )
    eng_id = r.headers["location"].split("/")[-1]

    page = client.get(f"/engagements/{eng_id}/replies").text
    assert "Reply detector disabled" in page
    assert "Poll Gmail for replies" not in page

    resp = client.post(f"/engagements/{eng_id}/poll-replies", follow_redirects=False)
    assert resp.status_code == 400


def test_cockpit_poll_button_visible_with_gmail_configured(tmp_path, monkeypatch):
    """With env vars + Gemini key set, the button shows and posting redirects
    to the replies page (we don't run a real poll — the gating is what we test)."""
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({
        "token": "tok", "refresh_token": "rt", "client_id": "c", "client_secret": "s",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/gmail.send"],
    }))
    monkeypatch.setenv("AUTOREACH_GMAIL_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("AUTOREACH_GMAIL_SENDER", "me@example.com")
    monkeypatch.setenv("AUTOREACH_GMAIL_DRY_RUN", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # makes GeminiClient happy

    from cockpit import create_app
    from fastapi.testclient import TestClient

    app = create_app(db_url=f"sqlite:///{tmp_path/'cock.db'}")
    # Inject a fake gmail builder so the poll doesn't try to hit the real API.
    app.state.reply_detector._gmail_build = lambda creds: _FakeGmailClient()
    # And a fake Gemini that won't be called (no inbound msgs configured).
    app.state.reply_detector._gemini = _FakeGeminiClient(
        {"classification": "interested", "suggested_reply": "x"}
    )
    # Override token loading so we don't actually hit google-auth.
    app.state.reply_detector._tokens = _FakeTokenStore()

    client = TestClient(app)
    r = client.post(
        "/engagements",
        data={
            "customer_name": "Gmail", "offer": "O", "icp_description": "I",
            "booking_url": "", "monthly_meeting_target": 0,
            "price_per_outcome_cents": 50000, "monthly_budget_cents": 0,
        },
        follow_redirects=False,
    )
    eng_id = r.headers["location"].split("/")[-1]

    page = client.get(f"/engagements/{eng_id}/replies").text
    assert "Poll Gmail for replies" in page
    assert "Reply detector disabled" not in page

    resp = client.post(f"/engagements/{eng_id}/poll-replies", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith(f"/engagements/{eng_id}/replies")

    # Banner shows the last poll summary.
    after = client.get(f"/engagements/{eng_id}/replies").text
    assert "Last Gmail poll" in after


# ─────────────────────────────────────────────────────────────────────────────
# Token store double — used by detector tests above
# ─────────────────────────────────────────────────────────────────────────────


class _FakeTokenStore:
    """Minimal GmailTokenStore for detector tests."""

    def __init__(self, *, creds: Any = None, raise_on_load: Any = None):
        self._creds = creds if creds is not None else object()
        self._raise = raise_on_load
        self._invalid = False

    def load(self):
        if self._raise is not None:
            raise self._raise
        return self._creds

    def save(self, c):
        pass

    def mark_invalid(self, reason: str):
        self._invalid = True

    def is_invalid(self) -> bool:
        return self._invalid
