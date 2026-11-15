"""Deliverability Guardian — pre-send spam + AI-fingerprint risk scoring."""

from __future__ import annotations

from engine.services.deliverability_guardian import (
    DeliverabilityGuardian,
    DraftRiskReport,
    RiskIssue,
)


def test_clean_human_draft_scores_green():
    g = DeliverabilityGuardian()
    r = g.score(
        subject="quick question about your Series A",
        body="Saw you closed your Series A last week. We help teams like yours "
             "book meetings without burning domains. Worth a 15-min chat?",
    )
    assert r.level == "green"
    assert r.score >= 78
    assert r.is_send_safe


def test_spammy_draft_is_blocked():
    g = DeliverabilityGuardian()
    r = g.score(
        subject="ACT NOW — 100% FREE GUARANTEED OFFER!!!",
        body="Click here to claim your FREE cash bonus. Limited time, act now! "
             "http://a.co http://b.co http://c.co Risk-free, no obligation.",
    )
    assert r.level == "block"
    assert not r.is_send_safe
    codes = {i.code for i in r.issues}
    assert "spam_words" in codes
    assert "link_density" in codes
    assert "shouting" in codes


def test_ai_tells_raise_fingerprint():
    g = DeliverabilityGuardian()
    r = g.score(
        subject="reaching out",
        body="I hope this email finds you well. I wanted to reach out to touch base "
             "and leverage some synergies to take your business to the next level.",
    )
    assert r.ai_fingerprint >= 40
    assert any(i.code == "ai_tells" for i in r.issues)


def test_ungrounded_copy_flagged_when_evidence_present():
    g = DeliverabilityGuardian()
    r = g.score(
        subject="hello there",
        body="We are a great company and would love to work with you sometime soon.",
        grounded_evidence=["funding_round detected for acme.com"],
    )
    assert any(i.code == "ungrounded" for i in r.issues)


def test_grounded_copy_not_flagged():
    g = DeliverabilityGuardian()
    r = g.score(
        subject="your funding_round",
        body="Congrats on the funding_round — timing looks right to talk. 15 min?",
        grounded_evidence=["funding_round"],
    )
    # 'congrats'/'funding' present → grounded; note 'funding_round' substring matches.
    assert not any(i.code == "ungrounded" for i in r.issues)


def test_llm_critic_hook_adds_issues():
    def critic(subject, body):
        return [RiskIssue("llm_ai_detected", "high", "Reads generated.", "Rewrite by hand.")]

    g = DeliverabilityGuardian(llm_critic=critic)
    r = g.score(subject="hi", body="A short human note. Worth a chat?")
    assert any(i.code == "llm_ai_detected" for i in r.issues)


def test_report_serializes():
    g = DeliverabilityGuardian()
    d = g.score(subject="x", body="y").as_dict()
    assert set(d) == {"score", "level", "ai_fingerprint", "issues"}
