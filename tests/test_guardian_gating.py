"""The Deliverability Guardian gates the outbound agent: a high-risk draft
ALWAYS requires human approval, even when the trust-ramp would auto-send."""

from __future__ import annotations

import pytest

from engine import Agent, Engagement, Prospect, open_storage
from engine.agents.outbound_agent import OutboundAgentV1
from engine.runtime.contexts import DefaultAgentContext


def _plan(tmp_path, *, subject, body):
    store, events, _ = open_storage(f"sqlite:///{tmp_path / 'g.db'}")
    store.save_engagement(Engagement(id="e", customer_name="X", offer="Our offer", icp_description="I"))
    store.save_agent(Agent(
        id="a", engagement_id="e", runner_kind=OutboundAgentV1.runner_kind,
        config={
            "hitl_threshold": 0,      # trust-ramp would NOT require approval
            "send_gap_seconds": 0,
            "personalize": False,     # no gemini → templates are the draft
            "subject_template": subject,
            "body_template": body,
        },
    ))
    store.save_prospect(Prospect(
        id="p", engagement_id="e", email="buyer@target.com",
        full_name="Jane Buyer", company="Target Co", status="new",
    ))
    ctx = DefaultAgentContext(store, events)
    return list(OutboundAgentV1().plan(store.get_agent("a"), context=ctx))


def test_spammy_draft_forces_approval_even_past_trust_ramp(tmp_path):
    jobs = _plan(
        tmp_path,
        subject="ACT NOW — 100% FREE GUARANTEED OFFER!!!",
        body="Click here for your FREE cash bonus now! Limited time, act now! "
             "http://a.co http://b.co http://c.co Risk-free, no obligation.",
    )
    assert len(jobs) == 1
    job = jobs[0]
    assert job.payload["deliverability_risk"]["level"] == "block"
    assert job.requires_approval is True  # forced by the Guardian despite hitl_threshold=0


def test_clean_draft_is_not_force_gated(tmp_path):
    jobs = _plan(
        tmp_path,
        subject="quick question, Jane",
        body="Hi Jane, saw Target Co is scaling. We help teams book meetings "
             "without hurting deliverability. Worth a short chat?",
    )
    assert len(jobs) == 1
    job = jobs[0]
    assert job.payload["deliverability_risk"]["level"] in {"green", "warn"}
    assert job.requires_approval is False  # trust-ramp off + not blocked → auto-eligible
