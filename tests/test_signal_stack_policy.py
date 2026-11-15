"""Signal Stack policy — the differentiator's core logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from engine.intent.models import IntentSignal
from engine.intent.signal_stack import SignalStackPolicy


def _sig(signal_type, domain="acme.com", *, hours_ago=1.0):
    return IntentSignal(
        tenant_id="t",
        signal_type=signal_type,
        company_domain=domain,
        payload={},
        timestamp=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )


def test_single_signal_qualifies_at_min_stack_1():
    d = SignalStackPolicy(min_stack=1).evaluate([_sig("funding_round")])
    assert d.qualifies
    assert d.depth == 1
    assert d.allowed_signal_types == {"funding_round"}


def test_min_stack_2_rejects_single_signal_type():
    p = SignalStackPolicy(min_stack=2)
    # One type (even repeated) is depth 1 → does NOT qualify.
    d = p.evaluate([_sig("funding_round"), _sig("funding_round", hours_ago=2)])
    assert not d.qualifies
    assert d.depth == 1
    assert "stack depth 1 < required 2" in d.reason


def test_min_stack_2_accepts_two_distinct_types():
    p = SignalStackPolicy(min_stack=2)
    d = p.evaluate([_sig("funding_round"), _sig("hiring_surge")])
    assert d.qualifies
    assert d.depth == 2
    assert d.allowed_signal_types == {"funding_round", "hiring_surge"}
    assert len(d.evidence) == 2  # both cited as grounding


def test_stale_signals_do_not_qualify():
    p = SignalStackPolicy(min_stack=1, freshness_hours=24)
    d = p.evaluate([_sig("funding_round", hours_ago=100)])  # older than the window
    assert not d.qualifies
    assert "stale" in d.reason


def test_score_rewards_depth_and_recency():
    p = SignalStackPolicy(min_stack=1, freshness_hours=336)
    deep_fresh = p.evaluate([_sig("a"), _sig("b"), _sig("c")])
    shallow_old = p.evaluate([_sig("a", hours_ago=300)])
    assert deep_fresh.score > shallow_old.score


def test_evidence_uses_latest_per_type():
    p = SignalStackPolicy(min_stack=1)
    d = p.evaluate([_sig("funding_round", hours_ago=48), _sig("funding_round", hours_ago=1)])
    assert d.depth == 1
    assert d.total_signals == 2
    # The evidence timestamp is the freshest instance of the type.
    assert d.age_hours < 2


def test_group_by_account_splits_domains():
    groups = SignalStackPolicy.group_by_account([
        _sig("funding_round", "a.com"),
        _sig("hiring_surge", "a.com"),
        _sig("funding_round", "b.com"),
    ])
    assert set(groups) == {"a.com", "b.com"}
    assert len(groups["a.com"]) == 2
