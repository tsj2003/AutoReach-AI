"""
Phase 1 integration tests.

Cover the real end-to-end loop:
    * SqliteStore / SqliteEventSink / SqliteCostLedger persistence
    * OutboundAgentV1 planning (idempotent across re-plans)
    * EngineRuntime tick + drain
    * HITL approval gate (trust ramp)
    * Retry semantics on retryable adapter failures
    * Dead-letter on non-retryable / exhausted retries
    * Restart durability (kill the runtime mid-run, resume from DB)
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from engine import (
    AdapterRegistry,
    Agent,
    ConsoleEmailAdapter,
    Engagement,
    EngineRuntime,
    Event,
    EventKind,
    Job,
    JobKind,
    JobState,
    OutboundAgentV1,
    Prospect,
    open_storage,
)
from engine.runtime.results import AdapterResultData


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def db_url(tmp_path):
    db_file = tmp_path / "engine_test.db"
    return f"sqlite:///{db_file}"


@pytest.fixture
def storage(db_url):
    return open_storage(db_url)


@pytest.fixture
def runtime_and_outbox(storage):
    store, events, ledger = storage
    console = ConsoleEmailAdapter()
    registry = AdapterRegistry([console])
    runners = {OutboundAgentV1.runner_kind: OutboundAgentV1()}
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=registry, agent_runners=runners,
    )
    return rt, console, store, events, ledger


def _seed_engagement(store, *, hitl_threshold=0, prospects=3, target=20):
    """Create an engagement, agent, and N prospects. Returns (eng, agent)."""
    eng = Engagement(
        id="eng_test",
        customer_name="Test Co",
        offer="Test offer",
        icp_description="Test ICP",
        monthly_meeting_target=target,
        price_per_outcome_cents=50_000,
        monthly_budget_cents=100_000,
    )
    store.save_engagement(eng)
    agent = Agent(
        id="agent_test",
        engagement_id=eng.id,
        runner_kind=OutboundAgentV1.runner_kind,
        config={
            "hitl_threshold": hitl_threshold,
            "send_gap_seconds": 0,  # tests don't sleep
            "subject_template": "Hello {to_name}",
            "body_template": "Hi {to_name}, here's the offer: {offer}",
        },
    )
    store.save_agent(agent)
    for i in range(prospects):
        store.save_prospect(
            Prospect(
                id=f"p_{i}",
                engagement_id=eng.id,
                email=f"prospect{i}@example.com",
                full_name=f"Prospect {i}",
                company=f"Company {i}",
            )
        )
    return eng, agent


# ─────────────────────────────────────────────────────────────────────────────
# Storage
# ─────────────────────────────────────────────────────────────────────────────


def test_engagement_roundtrip(storage):
    store, _, _ = storage
    eng = Engagement(
        id="eng_1", customer_name="X", offer="O", icp_description="I",
        monthly_meeting_target=10, price_per_outcome_cents=50_000,
    )
    store.save_engagement(eng)
    fetched = store.get_engagement("eng_1")
    assert fetched is not None
    assert fetched.id == "eng_1"
    assert fetched.monthly_meeting_target == 10
    assert fetched.price_per_outcome_cents == 50_000
    assert fetched.created_at.tzinfo is not None


def test_prospect_listing_filters_by_status(storage):
    store, _, _ = storage
    store.save_engagement(Engagement(
        id="eng_2", customer_name="X", offer="O", icp_description="I",
    ))
    for i, status in enumerate(["new", "new", "contacted"]):
        store.save_prospect(Prospect(
            id=f"p_{i}", engagement_id="eng_2",
            email=f"p{i}@x.com", status=status,
        ))
    new_only = list(store.list_prospects("eng_2", status="new"))
    assert len(new_only) == 2


def test_event_log_roundtrip(storage):
    _, events, _ = storage
    events.emit(Event(
        id="ev_1", kind=EventKind.ENGAGEMENT_CREATED,
        engagement_id="eng_1", payload={"k": "v"},
    ))
    rows = list(events.list_recent(engagement_id="eng_1"))
    assert len(rows) == 1
    assert rows[0].payload == {"k": "v"}
    assert rows[0].kind == EventKind.ENGAGEMENT_CREATED


def test_cost_ledger_budget_math(storage):
    store, _, ledger = storage
    eng = Engagement(
        id="eng_b", customer_name="X", offer="O", icp_description="I",
        monthly_budget_cents=1_000,
    )
    store.save_engagement(eng)
    from engine.core.types import CostEntry
    ledger.debit(CostEntry(id="c1", engagement_id="eng_b", job_id=None, category="llm", amount_cents=300))
    ledger.debit(CostEntry(id="c2", engagement_id="eng_b", job_id=None, category="email_send", amount_cents=200))
    assert ledger.total_spent_cents("eng_b") == 500
    assert ledger.total_spent_cents("eng_b", category="llm") == 300
    assert ledger.remaining_budget_cents("eng_b") == 500


def test_due_jobs_respects_scheduled_for(storage):
    store, _, _ = storage
    store.save_engagement(Engagement(id="e", customer_name="X", offer="O", icp_description="I"))
    store.save_agent(Agent(id="a", engagement_id="e", runner_kind="outbound.v1"))
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    past = datetime.now(timezone.utc) - timedelta(seconds=5)
    store.save_job(Job(
        id="j_future", engagement_id="e", agent_id="a",
        kind=JobKind.EMAIL_SEND, payload={}, scheduled_for=future,
    ))
    store.save_job(Job(
        id="j_past", engagement_id="e", agent_id="a",
        kind=JobKind.EMAIL_SEND, payload={}, scheduled_for=past,
    ))
    due = [j.id for j in store.list_due_jobs()]
    assert "j_past" in due
    assert "j_future" not in due


# ─────────────────────────────────────────────────────────────────────────────
# Outbound agent + runtime
# ─────────────────────────────────────────────────────────────────────────────


def test_outbound_agent_plans_one_job_per_new_prospect(runtime_and_outbox):
    rt, console, store, events, _ = runtime_and_outbox
    _seed_engagement(store, hitl_threshold=0, prospects=3)
    planned = rt.plan_all()
    assert planned == 3


def test_outbound_agent_planning_is_idempotent(runtime_and_outbox):
    rt, console, store, events, _ = runtime_and_outbox
    _seed_engagement(store, hitl_threshold=0, prospects=3)
    rt.plan_all()
    rt.plan_all()
    rt.plan_all()
    pending = list(store.list_jobs_by_state(JobState.PENDING.value))
    assert len(pending) == 3


def test_drain_sends_all_pending_jobs(runtime_and_outbox):
    rt, console, store, events, ledger = runtime_and_outbox
    _seed_engagement(store, hitl_threshold=0, prospects=4)
    result = rt.run_once()
    assert result["planned"] == 4
    assert result["executed"] >= 4
    assert len(console.outbox) == 4
    succeeded = list(store.list_jobs_by_state(JobState.SUCCEEDED.value))
    assert len(succeeded) == 4


def test_drain_renders_template_correctly(runtime_and_outbox):
    rt, console, store, events, _ = runtime_and_outbox
    _seed_engagement(store, hitl_threshold=0, prospects=1)
    rt.run_once()
    assert console.outbox[0]["subject"] == "Hello Prospect 0"
    assert "Test offer" in console.outbox[0]["body"]


def test_emits_full_event_lifecycle(runtime_and_outbox):
    rt, console, store, events, _ = runtime_and_outbox
    _seed_engagement(store, hitl_threshold=0, prospects=1)
    rt.run_once()
    kinds = [e.kind.value for e in events.list_recent(engagement_id="eng_test", limit=50)]
    assert "job.created" in kinds
    assert "job.started" in kinds
    assert "job.succeeded" in kinds
    assert "email.sent" in kinds


# ─────────────────────────────────────────────────────────────────────────────
# HITL trust ramp
# ─────────────────────────────────────────────────────────────────────────────


def test_hitl_blocks_first_send_when_threshold_above_zero(runtime_and_outbox):
    rt, console, store, events, _ = runtime_and_outbox
    _seed_engagement(store, hitl_threshold=50, prospects=1)
    rt.run_once()
    awaiting = list(store.list_jobs_by_state(JobState.AWAITING_APPROVAL.value))
    assert len(awaiting) == 1
    assert len(console.outbox) == 0  # nothing sent yet


def test_hitl_approve_resumes_send(runtime_and_outbox):
    rt, console, store, events, _ = runtime_and_outbox
    _seed_engagement(store, hitl_threshold=50, prospects=1)
    rt.run_once()
    awaiting = list(store.list_jobs_by_state(JobState.AWAITING_APPROVAL.value))
    assert len(awaiting) == 1
    job_id = awaiting[0].id
    assert rt.approve_job(job_id) is True
    rt.run_once()
    assert len(console.outbox) == 1
    assert any(j.state == JobState.SUCCEEDED.value
               for j in store.list_jobs_by_state(JobState.SUCCEEDED.value))


def test_hitl_reject_terminates_job(runtime_and_outbox):
    rt, console, store, events, _ = runtime_and_outbox
    _seed_engagement(store, hitl_threshold=50, prospects=1)
    rt.run_once()
    awaiting = list(store.list_jobs_by_state(JobState.AWAITING_APPROVAL.value))
    job_id = awaiting[0].id
    assert rt.reject_job(job_id, reason="test rejection") is True
    rejected = list(store.list_jobs_by_state(JobState.REJECTED.value))
    assert len(rejected) == 1
    assert rejected[0].last_error == "test rejection"
    rt.run_once()
    assert len(console.outbox) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Retry / dead-letter
# ─────────────────────────────────────────────────────────────────────────────


class _AlwaysRetryableFailureAdapter:
    name = "fail.retryable"

    def __init__(self):
        self.calls = 0

    def handles(self, job):
        return job.kind == JobKind.EMAIL_SEND

    def execute(self, job, *, context):
        self.calls += 1
        return AdapterResultData.fail("transient failure", retryable=True)


def test_retryable_failure_eventually_dead_letters(storage):
    store, events, ledger = storage
    failing = _AlwaysRetryableFailureAdapter()
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([failing]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, hitl_threshold=0, prospects=1)

    # Drive it manually — manually move scheduled_for back to "now" between
    # ticks so retries become due immediately.
    rt.tick()  # plan + first attempt -> fail -> retry scheduled in future
    for _ in range(5):
        # Pull all jobs and force them due.
        for j in list(store.list_jobs_by_state(JobState.PENDING.value)):
            j.scheduled_for = datetime.now(timezone.utc) - timedelta(seconds=1)
            store.save_job(j)
        rt.tick()

    dead = list(store.list_jobs_by_state(JobState.DEAD_LETTERED.value))
    assert len(dead) == 1
    assert dead[0].attempt == 3  # max_attempts default


class _NonRetryableFailureAdapter:
    name = "fail.fatal"

    def handles(self, job):
        return job.kind == JobKind.EMAIL_SEND

    def execute(self, job, *, context):
        return AdapterResultData.fail("bad input, do not retry", retryable=False)


def test_non_retryable_failure_dead_letters_on_first_attempt(storage):
    store, events, ledger = storage
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([_NonRetryableFailureAdapter()]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, hitl_threshold=0, prospects=1)
    rt.run_once()
    dead = list(store.list_jobs_by_state(JobState.DEAD_LETTERED.value))
    assert len(dead) == 1
    assert dead[0].attempt == 1
    assert "bad input" in (dead[0].last_error or "")


# ─────────────────────────────────────────────────────────────────────────────
# Restart durability
# ─────────────────────────────────────────────────────────────────────────────


def test_runtime_resumes_after_simulated_kill(tmp_path):
    """
    Simulate: process A creates jobs, dies before executing them.
    Process B opens the same DB, executes them, ends up with the same state
    we'd have if A hadn't died.
    """
    db_url = f"sqlite:///{tmp_path / 'kill.db'}"

    # ── process A ────────────────────────────────────────────────
    store_a, events_a, ledger_a = open_storage(db_url)
    rt_a = EngineRuntime(
        store=store_a, events=events_a, ledger=ledger_a,
        adapters=AdapterRegistry([ConsoleEmailAdapter()]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store_a, hitl_threshold=0, prospects=2)
    planned = rt_a.plan_all()
    assert planned == 2
    # A dies here, before executing. Drop references.
    del rt_a, store_a, events_a, ledger_a

    # ── process B ────────────────────────────────────────────────
    store_b, events_b, ledger_b = open_storage(db_url)
    console_b = ConsoleEmailAdapter()
    rt_b = EngineRuntime(
        store=store_b, events=events_b, ledger=ledger_b,
        adapters=AdapterRegistry([console_b]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    rt_b.run_once()
    assert len(console_b.outbox) == 2
    succeeded = list(store_b.list_jobs_by_state(JobState.SUCCEEDED.value))
    assert len(succeeded) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Adapter dispatch
# ─────────────────────────────────────────────────────────────────────────────


def test_no_adapter_dead_letters_immediately(storage):
    store, events, ledger = storage
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([]),  # no adapters!
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, hitl_threshold=0, prospects=1)
    rt.run_once()
    dead = list(store.list_jobs_by_state(JobState.DEAD_LETTERED.value))
    assert len(dead) == 1
    assert "no adapter" in (dead[0].last_error or "")


# ─────────────────────────────────────────────────────────────────────────────
# Gmail adapter (no real API calls — fakes the gmail client)
# ─────────────────────────────────────────────────────────────────────────────


class _FakeGmailClient:
    """Stand-in for googleapiclient build('gmail', ...). No network."""

    def __init__(self, *, message_id="msg_1", thread_id="thread_1", raise_on_send=None):
        self._message_id = message_id
        self._thread_id = thread_id
        self._raise = raise_on_send
        self.sent_payloads: list[dict] = []

    def users(self):
        return self

    def messages(self):
        return self

    def send(self, *, userId, body):
        self.sent_payloads.append({"userId": userId, "body": body})
        return self

    def execute(self):
        if self._raise is not None:
            raise self._raise
        return {"id": self._message_id, "threadId": self._thread_id}


def test_gmail_adapter_success_path(storage):
    from engine import GmailEmailAdapter

    store, events, ledger = storage
    fake_client = _FakeGmailClient()
    adapter = GmailEmailAdapter(
        sender_email="me@example.com",
        credentials_provider=lambda: object(),
        gmail_build=lambda creds: fake_client,
    )
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, hitl_threshold=0, prospects=1)
    rt.run_once()
    assert len(fake_client.sent_payloads) == 1
    raw_b64 = fake_client.sent_payloads[0]["body"]["raw"]
    import base64, email
    decoded = base64.urlsafe_b64decode(raw_b64.encode()).decode()
    # Subject is in the headers, plain text. Body is base64-MIME-encoded —
    # parse the message and pull the text/plain part out.
    msg = email.message_from_string(decoded)
    assert msg["Subject"] == "Hello Prospect 0"
    assert msg["To"] == "prospect0@example.com"
    text_parts = [
        p.get_payload(decode=True).decode("utf-8")
        for p in msg.walk()
        if p.get_content_type() == "text/plain"
    ]
    assert any("Test offer" in t for t in text_parts)
    succeeded = list(store.list_jobs_by_state(JobState.SUCCEEDED.value))
    assert len(succeeded) == 1
    assert succeeded[0].result.get("gmail_message_id") == "msg_1"
    # Cost ledger was debited.
    assert ledger.total_spent_cents("eng_test", category="email_send") == 1


def test_gmail_adapter_invalid_grant_is_non_retryable(storage):
    from engine import GmailEmailAdapter

    store, events, ledger = storage

    class _BoomError(Exception):
        pass

    fake_client = _FakeGmailClient(raise_on_send=_BoomError("invalid_grant: token expired"))
    adapter = GmailEmailAdapter(
        sender_email="me@example.com",
        credentials_provider=lambda: object(),
        gmail_build=lambda creds: fake_client,
    )
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([adapter]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    _seed_engagement(store, hitl_threshold=0, prospects=1)
    rt.run_once()
    dead = list(store.list_jobs_by_state(JobState.DEAD_LETTERED.value))
    assert len(dead) == 1
    assert dead[0].attempt == 1  # non-retryable, didn't retry
