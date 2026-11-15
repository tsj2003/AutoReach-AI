"""Extended reply categories (feature #1): OOO, referral, do_not_contact, not_interested."""

from __future__ import annotations

import json

import pytest

from engine import Engagement, open_storage
from engine.llm import GeminiResult
from engine.llm.classifier import classify_and_draft
from engine.services import OperationsService, ReplyActionExecutor


class _FakeGemini:
    def __init__(self, data):
        self._data = data

    def generate_json(self, *, prompt, **kw):
        return GeminiResult(data=dict(self._data), raw_text=json.dumps(self._data), model="fake")


# ── classifier ─────────────────────────────────────────────────────────────


def test_classify_out_of_office_extracts_return_date():
    fake = _FakeGemini({
        "classification": "out_of_office",
        "suggested_reply": "",
        "return_date": "2026-07-15",
    })
    out = classify_and_draft(snippet="I'm OOO until 2026-07-15", client=fake)
    assert out.classification == "out_of_office"
    assert out.return_date == "2026-07-15"
    assert out.suggested_reply == ""


def test_classify_ooo_regex_backstop_when_model_omits_date():
    fake = _FakeGemini({"classification": "out_of_office", "suggested_reply": "", "return_date": ""})
    out = classify_and_draft(snippet="On leave, back 2026-08-01, contact ops meanwhile", client=fake)
    assert out.return_date == "2026-08-01"


def test_classify_referral_extracts_email():
    fake = _FakeGemini({
        "classification": "referral", "suggested_reply": "Thanks — could you intro me?",
        "referred_email": "", "referred_name": "Jane",
    })
    out = classify_and_draft(snippet="You should talk to jane@acme.com, she owns this", client=fake)
    assert out.classification == "referral"
    assert out.referred_email == "jane@acme.com"  # regex backstop
    assert out.referred_name == "Jane"


def test_classify_do_not_contact():
    fake = _FakeGemini({"classification": "do_not_contact", "suggested_reply": "Removed you."})
    out = classify_and_draft(snippet="Remove me from your list immediately", client=fake)
    assert out.classification == "do_not_contact"


def test_classify_not_interested():
    fake = _FakeGemini({"classification": "not_interested", "suggested_reply": "Understood."})
    out = classify_and_draft(snippet="Not a fit for us right now", client=fake)
    assert out.classification == "not_interested"


# ── reply actions for new categories ─────────────────────────────────────────


@pytest.fixture
def kit(tmp_path):
    store, events, ledger = open_storage(f"sqlite:///{tmp_path/'cats.db'}")
    ops = OperationsService(store=store, events=events)
    store.save_engagement(Engagement(id="e", customer_name="C", offer="O", icp_description="I"))
    p = ops.add_prospect(engagement_id="e", email="x@y.com", full_name="X")
    return store, events, ledger, ops, p


def test_do_not_contact_unsubscribes(kit):
    store, events, ledger, ops, p = kit
    reply = ops.record_reply(engagement_id="e", prospect_id=p.id, snippet="remove me",
                             classification="do_not_contact")
    ex = ReplyActionExecutor(store=store, events=events)
    result = ex.handle(reply, mode="autopilot")
    assert result.action == "unsubscribed"
    assert store.get_prospect(p.id).status == "unsubscribed"


def test_not_interested_marks_dead(kit):
    store, events, ledger, ops, p = kit
    reply = ops.record_reply(engagement_id="e", prospect_id=p.id, snippet="not a fit",
                             classification="not_interested")
    ex = ReplyActionExecutor(store=store, events=events)
    result = ex.handle(reply, mode="autopilot")
    assert result.action == "not_interested"
    assert store.get_prospect(p.id).status == "dead"


def test_out_of_office_reschedules(kit):
    store, events, ledger, ops, p = kit
    reply = ops.record_reply(engagement_id="e", prospect_id=p.id,
                             snippet="OOO until 2026-09-01", classification="out_of_office")
    ex = ReplyActionExecutor(store=store, events=events)
    result = ex.handle(reply, mode="autopilot")
    assert result.action == "ooo_rescheduled"
    # Prospect stays contactable (not dead/unsubscribed), with a future next_send_after.
    refreshed = store.get_prospect(p.id)
    assert refreshed.status in ("contacted", "new", "replied")
    assert "next_send_after" in refreshed.raw


def test_referral_flags_for_operator(kit):
    store, events, ledger, ops, p = kit
    reply = ops.record_reply(engagement_id="e", prospect_id=p.id,
                             snippet="talk to jane@acme.com", classification="referral")
    ex = ReplyActionExecutor(store=store, events=events)
    result = ex.handle(reply, mode="autopilot")
    assert result.action == "flagged_for_approval"
