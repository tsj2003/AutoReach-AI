"""
Phase 0 smoke tests for the engine package.

These tests prove the abstractions actually work as intended — types are
constructible, the state machine guards transitions, the public surface is
importable. They're deliberately small; the real integration tests come in
Phase 1 once the storage and adapter implementations exist.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

import engine
from engine import (
    Agent,
    CostEntry,
    Engagement,
    Event,
    EventKind,
    Job,
    JobKind,
    JobState,
    JobStateMachine,
    Prospect,
)
from engine.core.state import IllegalTransition, TERMINAL_STATES


# ─────────────────────────────────────────────────────────────────────────────
# Public surface
# ─────────────────────────────────────────────────────────────────────────────


def test_engine_version_is_set():
    # Bumped to 0.1.0 with Phase 1 (storage + adapters + runtime).
    assert engine.__version__ == "0.1.0"


def test_public_surface_is_complete():
    expected = {
        # Protocols
        "Adapter", "AgentRunner", "CostLedger", "EventSink", "Store",
        # State
        "JobState", "JobStateMachine",
        # Types
        "Agent", "CostEntry", "Engagement", "Event", "EventKind",
        "Job", "JobKind", "Meeting", "Prospect", "Reply",
        # Runtime
        "AdapterRegistry", "AdapterResultData", "EngineRuntime",
        # Storage
        "SqliteStore", "SqliteEventSink", "SqliteCostLedger", "open_storage",
        # Adapters
        "ConsoleEmailAdapter", "GmailEmailAdapter", "RealGmailSendAdapter",
        "GmailTokenStore", "JsonFileTokenStore",
        "TokenInvalid", "TokenUnavailable",
        # Agent runners
        "OutboundAgentV1",
        # Meta
        "__version__",
    }
    assert set(engine.__all__) == expected


# ─────────────────────────────────────────────────────────────────────────────
# Domain types
# ─────────────────────────────────────────────────────────────────────────────


def test_engagement_construction_with_minimal_fields():
    e = Engagement(
        id="eng_1",
        customer_name="AutoReach (self)",
        offer="$500 per qualified meeting for B2B founders",
        icp_description="seed–series A B2B SaaS founders, US/EU, 5–50 employees",
    )
    assert e.id == "eng_1"
    assert e.status == "active"
    assert e.created_at.tzinfo is not None  # timezone-aware


def test_engagement_construction_with_billing_fields():
    e = Engagement(
        id="eng_2",
        customer_name="Friendly Co",
        offer="...",
        icp_description="...",
        monthly_meeting_target=20,
        price_per_outcome_cents=50_000,  # $500
        monthly_budget_cents=100_000,    # $1,000 cap
    )
    assert e.monthly_meeting_target == 20
    assert e.price_per_outcome_cents == 50_000
    assert e.monthly_budget_cents == 100_000


def test_prospect_defaults():
    p = Prospect(id="p_1", engagement_id="eng_1", email="a@b.com")
    assert p.status == "new"
    assert p.research == {}
    assert p.raw == {}


def test_agent_defaults():
    a = Agent(id="a_1", engagement_id="eng_1", runner_kind="outbound.v1")
    assert a.status == "active"
    assert a.config == {}


def test_job_defaults_to_pending():
    j = Job(
        id="j_1",
        engagement_id="eng_1",
        agent_id="a_1",
        kind=JobKind.EMAIL_SEND,
        payload={"to": "a@b.com"},
    )
    assert j.state == "pending"
    assert j.attempt == 0
    assert j.max_attempts == 3
    assert j.requires_approval is False


def test_event_is_frozen():
    e = Event(
        id="ev_1",
        kind=EventKind.JOB_CREATED,
        engagement_id="eng_1",
        job_id="j_1",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        e.kind = EventKind.JOB_FAILED  # type: ignore[misc]


def test_cost_entry_uses_integer_cents():
    c = CostEntry(
        id="c_1",
        engagement_id="eng_1",
        job_id="j_1",
        category="llm",
        amount_cents=42,
    )
    assert isinstance(c.amount_cents, int)
    assert c.amount_cents == 42


# ─────────────────────────────────────────────────────────────────────────────
# State machine
# ─────────────────────────────────────────────────────────────────────────────


def test_legal_transition_pending_to_running():
    assert JobStateMachine.can_transition(JobState.PENDING, JobState.RUNNING)
    assert JobStateMachine.transition(JobState.PENDING, JobState.RUNNING) == JobState.RUNNING


def test_legal_transition_running_to_succeeded():
    assert JobStateMachine.can_transition(JobState.RUNNING, JobState.SUCCEEDED)


def test_legal_transition_through_hitl_approval():
    # pending → awaiting_approval → approved → running
    assert JobStateMachine.can_transition(JobState.PENDING, JobState.AWAITING_APPROVAL)
    assert JobStateMachine.can_transition(JobState.AWAITING_APPROVAL, JobState.APPROVED)
    assert JobStateMachine.can_transition(JobState.APPROVED, JobState.RUNNING)


def test_legal_transition_failed_to_retry_to_pending():
    assert JobStateMachine.can_transition(JobState.FAILED, JobState.RETRY_SCHEDULED)
    assert JobStateMachine.can_transition(JobState.RETRY_SCHEDULED, JobState.PENDING)


def test_legal_transition_failed_to_dead_lettered():
    assert JobStateMachine.can_transition(JobState.FAILED, JobState.DEAD_LETTERED)


def test_illegal_transition_pending_to_succeeded():
    assert not JobStateMachine.can_transition(JobState.PENDING, JobState.SUCCEEDED)
    with pytest.raises(IllegalTransition):
        JobStateMachine.transition(JobState.PENDING, JobState.SUCCEEDED)


def test_illegal_transition_succeeded_to_anything():
    # Terminal state — nothing can leave it.
    for to_state in JobState:
        assert not JobStateMachine.can_transition(JobState.SUCCEEDED, to_state)


def test_illegal_transition_dead_lettered_to_anything():
    for to_state in JobState:
        assert not JobStateMachine.can_transition(JobState.DEAD_LETTERED, to_state)


def test_illegal_transition_rejected_to_anything():
    for to_state in JobState:
        assert not JobStateMachine.can_transition(JobState.REJECTED, to_state)


def test_terminal_states_are_correct():
    assert TERMINAL_STATES == frozenset({
        JobState.SUCCEEDED,
        JobState.REJECTED,
        JobState.DEAD_LETTERED,
    })
    for s in TERMINAL_STATES:
        assert JobStateMachine.is_terminal(s)


def test_state_machine_accepts_string_states():
    # Ergonomics: callers shouldn't have to import JobState everywhere.
    assert JobStateMachine.can_transition("pending", "running")
    assert JobStateMachine.transition("pending", "running") == JobState.RUNNING
