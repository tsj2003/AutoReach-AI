"""M6 — ReplyActionExecutor (HITL vs Autopilot) tests."""

from __future__ import annotations

import pytest

from engine import Engagement, Prospect, Reply, open_storage
from engine.services import OperationsService, ReplyActionExecutor


@pytest.fixture
def kit(tmp_path):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path/'m6.db'}")
    ops = OperationsService(store=store, events=events)
    store.save_engagement(Engagement(id="e", customer_name="C", offer="O", icp_description="I", booking_url="https://cal.com/x"))
    p = ops.add_prospect(engagement_id="e", email="ceo@target.com", full_name="CEO")
    return store, events, ledger, ops, p


def _reply(ops, p, classification, suggested="Book here: https://cal.com/x"):
    return ops.record_reply(
        engagement_id="e", prospect_id=p.id,
        snippet="...", classification=classification, suggested_reply=suggested,
    )


def test_interested_hitl_flags_for_approval(kit):
    store, events, ledger, ops, p = kit
    reply = _reply(ops, p, "interested")
    ex = ReplyActionExecutor(store=store, events=events)  # no send_fn
    result = ex.handle(reply, mode="hitl")
    assert result.action == "flagged_for_approval"
    assert result.auto_sent is False


def test_interested_autopilot_auto_sends(kit):
    store, events, ledger, ops, p = kit
    reply = _reply(ops, p, "interested")
    sent = {}
    def fake_send(r, body):
        sent["body"] = body
        return True
    ex = ReplyActionExecutor(store=store, events=events, send_fn=fake_send)
    result = ex.handle(reply, mode="autopilot")
    assert result.auto_sent is True
    assert "cal.com" in sent["body"]
    assert store.get_reply(reply.id).status == "sent"


def test_autopilot_send_failure_falls_back_to_flag(kit):
    store, events, ledger, ops, p = kit
    reply = _reply(ops, p, "interested")
    def failing_send(r, body):
        return False
    ex = ReplyActionExecutor(store=store, events=events, send_fn=failing_send)
    result = ex.handle(reply, mode="autopilot")
    assert result.auto_sent is False
    assert result.action == "flagged_for_approval"


def test_objection_never_auto_sends_even_in_autopilot(kit):
    store, events, ledger, ops, p = kit
    reply = _reply(ops, p, "objection")
    sent = {"called": False}
    def fake_send(r, body):
        sent["called"] = True
        return True
    ex = ReplyActionExecutor(store=store, events=events, send_fn=fake_send)
    result = ex.handle(reply, mode="autopilot")
    assert result.auto_sent is False
    assert sent["called"] is False


def test_unsubscribe_marks_prospect_and_stops(kit):
    store, events, ledger, ops, p = kit
    reply = _reply(ops, p, "unsubscribe", suggested="")
    ex = ReplyActionExecutor(store=store, events=events)
    result = ex.handle(reply, mode="autopilot")
    assert result.action == "unsubscribed"
    assert store.get_prospect(p.id).status == "unsubscribed"
