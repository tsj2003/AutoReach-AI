"""Merge fields + leftover-token fail-closed for outbound copy."""

from __future__ import annotations

from engine.adapters.email_gmail_real import RealGmailSendAdapter
from engine.adapters.email_merge import (
    copy_quality_error,
    first_name_from_payload,
    leftover_token_error,
    merge_email_copy,
)
from engine.adapters.gmail_token_store import TokenUnavailable
from engine.core.types import Job, JobKind
from engine.runtime.results import AdapterResultData
from engine.services.deliverability_guardian import DeliverabilityGuardian


class _UnusedTokens:
    def load(self):
        raise TokenUnavailable("token load should not run when copy fails closed")


def test_first_name_from_full_name():
    assert first_name_from_payload({"to_name": "Tarandeep Singh Juneja"}) == "Tarandeep"


def test_merge_replaces_first_name_and_company():
    subject, body, _html = merge_email_copy({
        "subject": "Hi {first_name}, streamline payments with Stripe",
        "body_text": "Hi {first_name}, I noticed {company} might benefit.",
        "to_name": "Tarandeep Singh Juneja",
        "company": "Juneja Trading Corporation",
    })
    assert subject == "Hi Tarandeep, streamline payments with Stripe"
    assert "Hi Tarandeep" in body
    assert "Juneja Trading Corporation" in body
    assert leftover_token_error(subject, body) is None


def test_leftover_unknown_token_fails():
    subject, body, _html = merge_email_copy({
        "subject": "Hi {first_name}",
        "body_text": "See {unknown_field}",
        "to_name": "Ada Lovelace",
    })
    assert leftover_token_error(subject, body) is not None


def test_generic_boilerplate_without_icp_fact_is_blocked():
    err = copy_quality_error({
        "subject": "Hi Tarandeep, streamline payments with Stripe",
        "body_text": "Stripe helps businesses of all sizes accept payments globally.",
        "first_name": "Tarandeep",
        "company": "Juneja Trading Corporation",
    })
    assert err and "generic" in err


def test_gmail_adapter_refuses_leftover_tokens():
    adapter = RealGmailSendAdapter(
        sender_email="from@test.com",
        token_store=_UnusedTokens(),
        dry_run=True,
    )
    job = Job(
        id="job_copy",
        engagement_id="eng",
        agent_id="agent",
        kind=JobKind.EMAIL_SEND,
        payload={
            "to_email": "to@test.com",
            "subject": "Hi {first_name}",
            "body_text": "Please read {secret_token}",
            "to_name": "Ada",
        },
    )

    class _Ctx:
        def emit(self, *_a, **_k):
            return None

    result = adapter.execute(job, context=_Ctx())
    assert isinstance(result, AdapterResultData)
    assert result.succeeded is False
    assert result.retryable is False
    assert "unrendered" in (result.error or "")


def test_gmail_adapter_merges_first_name_before_dry_run_fail_on_token_store():
    adapter = RealGmailSendAdapter(
        sender_email="from@test.com",
        token_store=_UnusedTokens(),
        dry_run=True,
    )
    job = Job(
        id="job_ok_copy",
        engagement_id="eng",
        agent_id="agent",
        kind=JobKind.EMAIL_SEND,
        payload={
            "to_email": "to@test.com",
            "subject_template": "Hi {first_name}, question",
            "body_template": "Hi {first_name}, I saw {company} and {icp_fact}.",
            "to_name": "Tarandeep Singh Juneja",
            "company": "Juneja Trading",
            "icp_fact": "payments for trading firms",
        },
    )

    class _Ctx:
        def emit(self, *_a, **_k):
            return None

    result = adapter.execute(job, context=_Ctx())
    # Copy passed; token store is dummy so send cannot complete.
    assert result.succeeded is False
    assert "unrendered" not in (result.error or "")


def test_guardian_blocks_unrendered_tokens():
    r = DeliverabilityGuardian().score(
        subject="Hi {first_name}",
        body="Hello there",
    )
    assert r.level == "block"
    assert any(i.code == "unrendered_token" for i in r.issues)


def test_approve_job_refuses_leftover_tokens():
    from engine import AdapterRegistry, ConsoleEmailAdapter, EngineRuntime, open_storage
    from engine.core.state import JobState
    from engine.core.types import Agent, Engagement, Job, JobKind

    store, events, ledger = open_storage("sqlite:///:memory:")
    store.save_engagement(Engagement(
        id="eng", customer_name="C", offer="O", icp_description="I",
    ))
    store.save_agent(Agent(id="agent", engagement_id="eng", runner_kind="outbound.v1", config={}))
    store.save_job(Job(
        id="job_leftover",
        engagement_id="eng",
        agent_id="agent",
        kind=JobKind.EMAIL_SEND,
        state=JobState.AWAITING_APPROVAL.value,
        payload={
            "to_email": "to@test.com",
            "subject": "Hi {first_name}",
            "body_text": "Please read {secret_token}",
            "to_name": "Ada Lovelace",
            "company": "Acme",
        },
        requires_approval=True,
    ))
    rt = EngineRuntime(
        store=store,
        events=events,
        ledger=ledger,
        adapters=AdapterRegistry([ConsoleEmailAdapter()]),
        agent_runners={},
    )
    assert rt.approve_job("job_leftover") is True
    job = store.get_job("job_leftover")
    assert job.state == JobState.AWAITING_APPROVAL.value
    assert "unrendered" in (job.last_error or "")
    assert job.payload.get("copy_quality_error")


def test_approve_job_refuses_generic_boilerplate():
    from engine import AdapterRegistry, ConsoleEmailAdapter, EngineRuntime, open_storage
    from engine.core.state import JobState
    from engine.core.types import Agent, Engagement, Job, JobKind

    store, events, ledger = open_storage("sqlite:///:memory:")
    store.save_engagement(Engagement(
        id="eng", customer_name="C", offer="O", icp_description="I",
    ))
    store.save_agent(Agent(id="agent", engagement_id="eng", runner_kind="outbound.v1", config={}))
    store.save_job(Job(
        id="job_generic",
        engagement_id="eng",
        agent_id="agent",
        kind=JobKind.EMAIL_SEND,
        state=JobState.AWAITING_APPROVAL.value,
        payload={
            "to_email": "to@test.com",
            "subject": "Hi Tarandeep, streamline payments with Stripe",
            "body_text": "Stripe helps businesses of all sizes accept payments globally.",
            "first_name": "Tarandeep",
            "to_name": "Tarandeep Singh Juneja",
            "company": "Juneja Trading Corporation",
        },
        requires_approval=True,
    ))
    rt = EngineRuntime(
        store=store,
        events=events,
        ledger=ledger,
        adapters=AdapterRegistry([ConsoleEmailAdapter()]),
        agent_runners={},
    )
    assert rt.approve_job("job_generic") is True
    job = store.get_job("job_generic")
    assert job.state == JobState.AWAITING_APPROVAL.value
    assert "generic" in (job.last_error or "")


def test_approve_job_sends_merged_grounded_copy():
    from engine import AdapterRegistry, ConsoleEmailAdapter, EngineRuntime, open_storage
    from engine.core.state import JobState
    from engine.core.types import Agent, Engagement, Job, JobKind

    store, events, ledger = open_storage("sqlite:///:memory:")
    store.save_engagement(Engagement(
        id="eng", customer_name="C", offer="O", icp_description="I",
    ))
    store.save_agent(Agent(id="agent", engagement_id="eng", runner_kind="outbound.v1", config={}))
    console = ConsoleEmailAdapter()
    store.save_job(Job(
        id="job_ok",
        engagement_id="eng",
        agent_id="agent",
        kind=JobKind.EMAIL_SEND,
        state=JobState.AWAITING_APPROVAL.value,
        payload={
            "to_email": "to@test.com",
            "subject": "Hi {first_name}, question about trading ops",
            "body_text": "Hi {first_name}, I saw Juneja Trading Corporation needs payments for trading firms.",
            "to_name": "Tarandeep Singh Juneja",
            "company": "Juneja Trading Corporation",
            "icp_fact": "payments for trading firms",
        },
        requires_approval=True,
    ))
    rt = EngineRuntime(
        store=store,
        events=events,
        ledger=ledger,
        adapters=AdapterRegistry([console]),
        agent_runners={},
    )
    assert rt.approve_job("job_ok") is True
    job = store.get_job("job_ok")
    assert job.state == JobState.SUCCEEDED.value
    assert job.payload["subject"].startswith("Hi Tarandeep")
    assert "{first_name}" not in job.payload["subject"]
    assert console.outbox[0]["subject"].startswith("Hi Tarandeep")


def test_guardian_blocks_generic_boilerplate():
    r = DeliverabilityGuardian().score(
        subject="streamline payments with Stripe",
        body="Stripe helps businesses of all sizes accept payments globally.",
    )
    assert r.level == "block"
    assert any(i.code == "generic_boilerplate" for i in r.issues)
