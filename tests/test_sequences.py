"""Multi-step email sequences (follow-ups) — OutboundAgentV1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from engine import (
    AdapterRegistry, Agent, ConsoleEmailAdapter, Engagement, EngineRuntime,
    Event, EventKind, JobState, OutboundAgentV1, Prospect, open_storage,
)


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path/'seq.db'}")


def _runtime(storage):
    store, events, ledger = storage
    return EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([ConsoleEmailAdapter()]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    ), store, events, ledger


SEQUENCE = [
    {"subject_template": "Hi {first_name}", "body_template": "First touch {offer}"},
    {"wait_days": 3, "subject_template": "Re: Hi", "body_template": "Follow-up 1"},
    {"wait_days": 5, "subject_template": "Last note", "body_template": "Follow-up 2"},
]


def _seed(store, *, sequence=SEQUENCE, prospects=1):
    eng = Engagement(id="e", customer_name="C", offer="O", icp_description="I")
    store.save_engagement(eng)
    store.save_agent(Agent(
        id="a", engagement_id="e", runner_kind="outbound.v1",
        config={"hitl_threshold": 0, "send_gap_seconds": 0, "sequence": sequence},
    ))
    for i in range(prospects):
        store.save_prospect(Prospect(id=f"p{i}", engagement_id="e", email=f"p{i}@x.com", full_name=f"P{i}"))
    return eng


def test_step1_sends_first_touch(storage):
    rt, store, events, ledger = _runtime(storage)
    _seed(store, prospects=1)
    rt.run_once()
    succeeded = list(store.list_jobs_by_state(JobState.SUCCEEDED.value))
    assert len(succeeded) == 1
    assert succeeded[0].payload["step"] == 1
    # Prospect advanced to contacted.
    assert store.get_prospect("p0").status == "contacted"


def test_step2_not_sent_before_delay(storage):
    rt, store, events, ledger = _runtime(storage)
    _seed(store, prospects=1)
    rt.run_once()  # step 1
    rt.run_once()  # try again immediately — step 2 not due (3-day wait)
    succeeded = list(store.list_jobs_by_state(JobState.SUCCEEDED.value))
    assert len(succeeded) == 1  # still only step 1


def test_step2_sent_after_delay_elapses(storage):
    rt, store, events, ledger = _runtime(storage)
    _seed(store, prospects=1)
    rt.run_once()  # step 1

    # Backdate the step-1 EMAIL_SENT event to 4 days ago so step 2 (3-day wait) is due.
    # Rewrite the event row's occurred_at.
    from engine.storage.sqlite import events_table
    old = datetime.now(timezone.utc) - timedelta(days=4)
    with store._holder.conn() as c:
        c.execute(events_table.update().where(events_table.c.kind == "email.sent").values(occurred_at=old))

    rt.run_once()  # step 2 should now be due
    succeeded = list(store.list_jobs_by_state(JobState.SUCCEEDED.value))
    steps = sorted(j.payload["step"] for j in succeeded)
    assert steps == [1, 2]


def test_replied_prospect_stops_sequence(storage):
    rt, store, events, ledger = _runtime(storage)
    _seed(store, prospects=1)
    rt.run_once()  # step 1
    # Mark prospect replied.
    p = store.get_prospect("p0")
    store.save_prospect(Prospect(
        id=p.id, engagement_id=p.engagement_id, email=p.email, full_name=p.full_name,
        company=p.company, title=p.title, raw=p.raw, research=p.research,
        status="replied", created_at=p.created_at,
    ))
    # Backdate so step 2 would otherwise be due.
    from engine.storage.sqlite import events_table
    old = datetime.now(timezone.utc) - timedelta(days=10)
    with store._holder.conn() as c:
        c.execute(events_table.update().where(events_table.c.kind == "email.sent").values(occurred_at=old))
    rt.run_once()
    succeeded = list(store.list_jobs_by_state(JobState.SUCCEEDED.value))
    assert len(succeeded) == 1  # sequence halted — no step 2


def test_sequence_completes_after_all_steps(storage):
    rt, store, events, ledger = _runtime(storage)
    _seed(store, prospects=1)
    from engine.storage.sqlite import events_table

    # Run all 3 steps by repeatedly backdating sent events.
    for _ in range(4):
        with store._holder.conn() as c:
            old = datetime.now(timezone.utc) - timedelta(days=10)
            c.execute(events_table.update().where(events_table.c.kind == "email.sent").values(occurred_at=old))
        rt.run_once()

    succeeded = list(store.list_jobs_by_state(JobState.SUCCEEDED.value))
    steps = sorted(j.payload["step"] for j in succeeded)
    assert steps == [1, 2, 3]  # all three, no fourth


def test_backward_compat_no_sequence_single_send(storage):
    """No `sequence` config → single first-touch email, as before."""
    store, events, ledger = storage
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([ConsoleEmailAdapter()]),
        agent_runners={OutboundAgentV1.runner_kind: OutboundAgentV1()},
    )
    store.save_engagement(Engagement(id="e", customer_name="C", offer="O", icp_description="I"))
    store.save_agent(Agent(id="a", engagement_id="e", runner_kind="outbound.v1",
                           config={"hitl_threshold": 0, "send_gap_seconds": 0,
                                   "subject_template": "Hi", "body_template": "Body"}))
    store.save_prospect(Prospect(id="p", engagement_id="e", email="x@y.com"))
    for _ in range(3):
        rt.run_once()
    succeeded = list(store.list_jobs_by_state(JobState.SUCCEEDED.value))
    assert len(succeeded) == 1  # only one send, ever
