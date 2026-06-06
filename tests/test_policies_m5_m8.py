"""M5 (rate limits + plan tiers) and M8 (ESP matching) tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine import Engagement, Event, EventKind, open_storage
from engine.policies import EspMatcher, SendRateLimiter, get_plan_limits


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path/'pol.db'}")


# ── Plan limits ────────────────────────────────────────────────────────────


def test_plan_limits_free_defaults():
    p = get_plan_limits("free")
    assert p.max_campaigns == 1
    assert p.personalization is False


def test_plan_limits_unknown_falls_back_to_free():
    assert get_plan_limits("nonsense").plan == "free"


def test_plan_limits_pro_allows_personalization():
    assert get_plan_limits("pro").personalization is True


# ── Rate limiter ───────────────────────────────────────────────────────────


def _seed(store, events, *, max_per_day=200, win_start=0, win_end=24):
    eng = Engagement(
        id="eng_rl", customer_name="RL", offer="O", icp_description="I",
        metadata={
            "max_emails_per_day": max_per_day,
            "sending_window_start": win_start,
            "sending_window_end": win_end,
        },
    )
    store.save_engagement(eng)
    return eng


def test_rate_limiter_allows_when_under_cap(storage):
    store, events, ledger = storage
    _seed(store, events, max_per_day=10)
    rl = SendRateLimiter(store=store, events=events)
    assert rl.can_send("eng_rl").allowed is True


def test_rate_limiter_blocks_when_cap_reached(storage):
    store, events, ledger = storage
    _seed(store, events, max_per_day=2)
    rl = SendRateLimiter(store=store, events=events)
    # Emit 2 sends today.
    for i in range(2):
        events.emit(Event(id=f"ev{i}", kind=EventKind.EMAIL_SENT, engagement_id="eng_rl"))
    decision = rl.can_send("eng_rl")
    assert decision.allowed is False
    assert "cap" in decision.reason
    assert decision.retry_after_seconds and decision.retry_after_seconds > 0


def test_rate_limiter_missing_engagement(storage):
    store, events, ledger = storage
    rl = SendRateLimiter(store=store, events=events)
    assert rl.can_send("nope").allowed is False


# ── ESP matcher ────────────────────────────────────────────────────────────


def test_esp_matcher_heuristic_gmail():
    m = EspMatcher()
    # No DNS in test env → falls back to domain heuristic.
    assert m.detect_provider("someone@gmail.com") == "google"


def test_esp_matcher_unknown_is_other():
    m = EspMatcher()
    assert m.detect_provider("someone@somerandomdomain12345.xyz") == "other"


def test_esp_matcher_caches(monkeypatch):
    m = EspMatcher()
    calls = {"n": 0}
    orig = m._lookup

    def counting_lookup(domain):
        calls["n"] += 1
        return orig(domain)

    m._lookup = counting_lookup
    m.detect_provider("a@gmail.com")
    m.detect_provider("a@gmail.com")
    assert calls["n"] == 1  # second call served from cache


def test_esp_select_mailbox_prefers_match():
    m = EspMatcher()

    class MB:
        def __init__(self, provider):
            self.provider = provider

    boxes = [MB("microsoft"), MB("google")]
    chosen = m.select_mailbox("x@gmail.com", boxes)
    assert chosen.provider == "google"


def test_esp_select_mailbox_falls_back_to_first():
    m = EspMatcher()

    class MB:
        def __init__(self, provider):
            self.provider = provider

    boxes = [MB("zoho")]
    chosen = m.select_mailbox("x@gmail.com", boxes)
    assert chosen.provider == "zoho"


def test_esp_select_mailbox_empty_returns_none():
    assert EspMatcher().select_mailbox("x@y.com", []) is None
