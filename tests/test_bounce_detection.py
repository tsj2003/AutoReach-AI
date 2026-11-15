"""Bounce detection: DSN messages must feed EMAIL_BOUNCED into mailbox health,
never be treated as prospect replies — the guard against burning a domain."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine import EventKind, open_storage
from engine.services.bounce_detector import extract_failed_recipient, is_bounce_message
from engine.services.mailbox_health import MailboxHealthMonitor
from engine.services.reply_detector import GmailReplyDetector, ReplyDetectionResult


def test_is_bounce_message_detects_daemon_senders():
    assert is_bounce_message("Mail Delivery Subsystem <mailer-daemon@googlemail.com>", "Delivery Status Notification (Failure)")
    assert is_bounce_message("postmaster@outlook.com", "Undeliverable: Quick question")
    assert is_bounce_message("MAILER-DAEMON@x", "")


def test_is_bounce_message_ignores_real_replies():
    assert not is_bounce_message("Jane Buyer <jane@acme.com>", "Re: Quick question")
    assert not is_bounce_message("ceo@target.com", "interested, let's talk")


def test_extract_failed_recipient_skips_daemon_addresses():
    body = "Your message to buyer@target.com could not be delivered. mailer-daemon@googlemail.com"
    assert extract_failed_recipient(body) == "buyer@target.com"


def _detector_with_thread(store, events, messages):
    """Build a GmailReplyDetector whose Gmail client returns one canned thread."""
    class _Threads:
        def get(self, **kwargs):
            class _Exec:
                def execute(_self):
                    return {"messages": messages}
            return _Exec()

    class _Users:
        def threads(self):
            return _Threads()

    class _Gmail:
        def users(self):
            return _Users()

    from engine.services.operations import OperationsService

    ops = OperationsService(store=store, events=events)
    det = GmailReplyDetector(
        store=store, events=events, ledger=_NoLedger(), ops=ops,
        token_store=None, sender_email="me@myco.com",
        mailbox_id="mbx-1", gmail_build=lambda creds: _Gmail(),
    )
    return det


class _NoLedger:
    def debit(self, *a, **k):
        pass


def test_bounce_in_thread_emits_email_bounced_and_is_not_a_reply(tmp_path):
    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'b.db'}")

    class _Prospect:
        id = "p1"
        email = "buyer@target.com"

    bounce_msg = {
        "id": "m-bounce",
        "payload": {"headers": [
            {"name": "From", "value": "Mail Delivery Subsystem <mailer-daemon@googlemail.com>"},
            {"name": "Subject", "value": "Delivery Status Notification (Failure)"},
        ]},
        "snippet": "Your message to buyer@target.com could not be delivered.",
    }
    det = _detector_with_thread(store, events, [bounce_msg])
    result = ReplyDetectionResult()
    det._poll_one_thread(
        engagement_id="e1", prospect=_Prospect(), thread_id="t1",
        booking_url="", gmail=det._build_gmail(None), result=result,
    )

    assert result.bounces_detected == 1
    assert result.replies_recorded == 0
    bounced = [e for e in events.list_recent(limit=50) if e.kind == EventKind.EMAIL_BOUNCED]
    assert len(bounced) == 1
    assert bounced[0].payload["mailbox_id"] == "mbx-1"
    assert bounced[0].payload["failed_recipient"] == "buyer@target.com"


def test_bounces_drive_mailbox_unhealthy(tmp_path):
    """The recorded bounces flow into check_health and mark the mailbox unhealthy."""
    from engine.auth.mailbox_models import Mailbox
    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'bh.db'}")
    now = datetime.now(timezone.utc)
    store.save_mailbox(Mailbox(id="mbx-1", tenant_id="t", email_address="me@myco.com",
                               status="active", created_at=now, updated_at=now))
    from engine.core.types import Event
    for i in range(10):
        events.emit(Event(id=f"s{i}", kind=EventKind.EMAIL_SENT, engagement_id="e",
                          payload={"mailbox_id": "mbx-1"}))
    for i in range(3):
        events.emit(Event(id=f"b{i}", kind=EventKind.EMAIL_BOUNCED, engagement_id="e",
                          payload={"mailbox_id": "mbx-1", "mailbox_email": "me@myco.com"}))
    status = MailboxHealthMonitor(store=store, events=events).check_health("mbx-1")
    assert status.healthy is False  # 3/10 = 30% > 5% threshold
