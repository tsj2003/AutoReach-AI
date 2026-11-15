"""Reply send idempotency — no duplicate sends on retry or double-approve."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from engine.core.state import JobState
from engine.core.types import Engagement, Job, JobKind, Prospect, Reply
from engine.runtime.results import AdapterResultData
from engine.services.reply_sender import ReplySender, reply_send_job_id


@pytest.fixture
def reply_context(tmp_path):
    from engine import open_storage

    store, events, ledger = open_storage(f"sqlite:///{tmp_path / 'reply_idem.db'}")
    eng = Engagement(id="eng-1", customer_name="Co", offer="O", icp_description="I")
    store.save_engagement(eng, tenant_id="t1")
    prospect = Prospect(
        id="pro-1",
        engagement_id="eng-1",
        email="target@example.com",
        full_name="Target",
    )
    store.save_prospect(prospect)
    reply = Reply(
        id="rep-1",
        engagement_id="eng-1",
        prospect_id="pro-1",
        job_id=None,
        snippet="Interested",
        classification="interested",
        suggested_reply="Thanks — let's talk.",
        status="pending",
    )
    store.save_reply(reply)
    return store, events, ledger, reply


def test_reply_send_uses_deterministic_job_id():
    assert reply_send_job_id("rep-abc") == "reply_send_rep-abc"


def test_reply_send_skips_when_reply_already_sent(reply_context, monkeypatch):
    store, events, ledger, reply = reply_context
    sent = Reply(**{**reply.__dict__, "status": "sent"})
    sender = ReplySender(store=store, events=events, ledger=ledger)
    assert sender.send(sent, "body", tenant_id="t1") is True
    assert store.get_job(reply_send_job_id(reply.id)) is None


def test_reply_send_skips_when_job_already_succeeded(reply_context, monkeypatch):
    store, events, ledger, reply = reply_context
    job_id = reply_send_job_id(reply.id)
    store.save_job(
        Job(
            id=job_id,
            engagement_id=reply.engagement_id,
            agent_id="inbox_reply",
            kind=JobKind.EMAIL_REPLY_SEND,
            payload={"reply_id": reply.id},
            state=JobState.SUCCEEDED.value,
            prospect_id=reply.prospect_id,
            result={"sent": True},
        )
    )
    sender = ReplySender(store=store, events=events, ledger=ledger)
    assert sender.send(reply, "body", tenant_id="t1") is True


def test_reply_send_retries_after_failed_job(reply_context, monkeypatch):
    store, events, ledger, reply = reply_context
    job_id = reply_send_job_id(reply.id)
    store.save_job(
        Job(
            id=job_id,
            engagement_id=reply.engagement_id,
            agent_id="inbox_reply",
            kind=JobKind.EMAIL_REPLY_SEND,
            payload={"reply_id": reply.id},
            state=JobState.FAILED.value,
            prospect_id=reply.prospect_id,
        )
    )

    class FakeMailbox:
        id = "mb-1"
        email_address = "sender@example.com"

    store.list_mailboxes = MagicMock(return_value=[FakeMailbox()])

    adapter_result = AdapterResultData.ok(dry_run=True, sent=False)

    class FakeAdapter:
        def execute(self, job, context=None):
            return adapter_result

    monkeypatch.setenv("AUTOREACH_GMAIL_DRY_RUN", "1")
    monkeypatch.setattr(
        "engine.services.reply_sender.RealGmailSendAdapter",
        lambda **kwargs: FakeAdapter(),
    )

    sender = ReplySender(store=store, events=events, ledger=ledger)
    assert sender.send(reply, "body", tenant_id="t1") is True
    job = store.get_job(job_id)
    assert job.state == JobState.SUCCEEDED.value
