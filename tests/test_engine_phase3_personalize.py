"""
Phase 3 step 6 — outbound personalization (Gemini-powered template rewrite).

We don't hit live Gemini; tests inject a FakeGeminiClient.

Coverage:
    * personalize_outbound: happy path, fallback, length sanity, no-fields short-circuit
    * Reverse-targeting safety: unsafe raw fields are NOT exposed to Gemini
    * OutboundAgentV1: with personalization on, Job.payload has pre-rendered subject/body
    * OutboundAgentV1: without a GeminiClient, behavior is unchanged from Phase 1
    * Cost ledger is debited per personalized Job
    * Cockpit / runtime unaffected — full suite still green
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from engine import (
    AdapterRegistry,
    Agent,
    ConsoleEmailAdapter,
    Engagement,
    EngineRuntime,
    JobState,
    OutboundAgentV1,
    Prospect,
    open_storage,
)
from engine.llm import (
    GeminiError,
    GeminiResult,
    GeminiUnavailable,
    PersonalizationResult,
    personalize_outbound,
)


class _FakeGemini:
    """Drop-in GeminiClient with scripted responses."""

    def __init__(self, response):
        self._response = response
        self.calls: list[str] = []

    @property
    def has_api_key(self):
        return True

    def generate_json(self, *, prompt: str, **_kw):
        self.calls.append(prompt)
        if isinstance(self._response, Exception):
            raise self._response
        return GeminiResult(
            data=dict(self._response),
            raw_text=json.dumps(self._response),
            model="fake",
        )


@pytest.fixture
def storage(tmp_path):
    return open_storage(f"sqlite:///{tmp_path/'p3p.db'}")


# ─────────────────────────────────────────────────────────────────────────────
# personalize_outbound — pure unit tests
# ─────────────────────────────────────────────────────────────────────────────


def test_personalize_happy_path_uses_provided_fields():
    fake = _FakeGemini({
        "subject": "Quick thought for Alice at Acme",
        "body": "Hi Alice,\n\nFollowing up on the offer.\n\nBest,\nMe",
    })
    out = personalize_outbound(
        subject_template="Quick question for {first_name}",
        body_template="Hi {first_name}, here's the pitch.",
        prospect_fields={
            "full_name": "Alice Founder",
            "title": "CEO",
            "company": "Acme",
            "raw": {"city": "Bangalore"},
        },
        client=fake,
    )
    assert out.fallback_used is False
    assert out.error is None
    assert "Alice" in out.subject
    assert "Acme" in out.subject
    assert out.estimated_cost_cents >= 1
    assert "first_name" in out.used_fields
    assert "company" in out.used_fields
    assert "city" in out.used_fields  # whitelisted raw key

    # The prompt must include the field map but NOT unsafe raw keys.
    prompt = fake.calls[0]
    assert "Alice" in prompt
    assert "Acme" in prompt


def test_personalize_does_not_leak_unsafe_raw_fields_to_gemini():
    """
    Reverse-targeting safety: the raw CSV row may contain things the engine
    must not feed to the LLM (internal IDs, status flags, scraped notes,
    revenue estimates, etc.). Only an explicit whitelist passes through.
    """
    fake = _FakeGemini({"subject": "x", "body": "y"})
    out = personalize_outbound(
        subject_template="Hi {first_name}",
        body_template="Hi {first_name}",
        prospect_fields={
            "full_name": "Alice",
            "company": "Acme",
            "raw": {
                "company": "Acme",  # OK — already canonical
                "internal_score": "98",  # NOT whitelisted — must not leak
                "salary_range_estimate": "$200k-$300k",  # NOT whitelisted
                "private_note": "high priority — close fast",  # NOT whitelisted
                "city": "SF",  # whitelisted
            },
        },
        client=fake,
    )
    prompt = fake.calls[0]
    assert "Acme" in prompt
    assert "SF" in prompt
    assert "98" not in prompt
    assert "salary" not in prompt
    assert "private_note" not in prompt
    assert "internal_score" not in prompt
    assert "internal_score" not in out.used_fields


def test_personalize_short_circuits_when_no_useful_fields():
    """No name, no company, no title, no whitelisted raw — skip LLM call entirely."""
    fake = _FakeGemini({"subject": "shouldn't be called", "body": "shouldn't"})
    out = personalize_outbound(
        subject_template="Hi {first_name}",
        body_template="Body {first_name}",
        prospect_fields={"raw": {"random_unrelated": "x"}},
        client=fake,
    )
    assert fake.calls == []  # no LLM call made
    assert out.fallback_used is True
    assert out.estimated_cost_cents == 0
    assert "no usable" in (out.error or "").lower()


def test_personalize_fallback_on_gemini_unavailable():
    fake = _FakeGemini(GeminiUnavailable("no key"))
    out = personalize_outbound(
        subject_template="Hi {first_name}",
        body_template="Hi {first_name}, intro",
        prospect_fields={"full_name": "Bob", "company": "Beta"},
        client=fake,
    )
    assert out.fallback_used is True
    # Falls back to placeholder-substituted template.
    assert "Bob" in out.subject
    assert "Bob" in out.body_text


def test_personalize_fallback_on_gemini_error():
    fake = _FakeGemini(GeminiError("network"))
    out = personalize_outbound(
        subject_template="Hi {first_name}",
        body_template="Body",
        prospect_fields={"full_name": "Bob", "company": "Beta"},
        client=fake,
    )
    assert out.fallback_used is True
    assert "Bob" in out.subject


def test_personalize_rejects_empty_response_from_gemini():
    fake = _FakeGemini({"subject": "", "body": ""})
    out = personalize_outbound(
        subject_template="Hi {first_name}",
        body_template="Body",
        prospect_fields={"full_name": "Bob"},
        client=fake,
    )
    assert out.fallback_used is True
    assert "empty" in (out.error or "").lower()


def test_personalize_caps_runaway_subject_length():
    runaway = "x" * 500
    fake = _FakeGemini({"subject": runaway, "body": "ok body"})
    out = personalize_outbound(
        subject_template="Hi {first_name}",
        body_template="Body",
        prospect_fields={"full_name": "Bob"},
        client=fake,
    )
    assert out.fallback_used is False
    # Was truncated, not allowed to balloon.
    assert len(out.subject) <= 80


# ─────────────────────────────────────────────────────────────────────────────
# OutboundAgentV1 with personalization wired in
# ─────────────────────────────────────────────────────────────────────────────


def _seed(store, *, prospects=2):
    eng = Engagement(
        id="eng_p", customer_name="Personal", offer="The offer",
        icp_description="ICP",
        price_per_outcome_cents=50_000,
        monthly_budget_cents=100_000,
    )
    store.save_engagement(eng)
    agent = Agent(
        id="agent_p", engagement_id=eng.id, runner_kind=OutboundAgentV1.runner_kind,
        config={
            "hitl_threshold": 0,
            "send_gap_seconds": 0,
            "subject_template": "Quick question for {first_name}",
            "body_template": "Hi {first_name},\n\n{offer}\n\nWorth a chat?",
        },
    )
    store.save_agent(agent)
    sample_names = ["Alice", "Bob", "Carol", "Dan"]
    sample_companies = ["Acme", "Beta", "Cygnus", "Delta"]
    for i in range(prospects):
        store.save_prospect(Prospect(
            id=f"p_{i}", engagement_id=eng.id,
            email=f"p{i}@example.com",
            full_name=f"{sample_names[i]} Founder",
            company=sample_companies[i],
            title="Founder",
        ))
    return eng, agent


def test_agent_with_gemini_personalizes_payload(storage):
    store, events, ledger = storage
    fake_gemini = _FakeGemini({
        "subject": "PERSONALIZED-SUBJECT",
        "body": "PERSONALIZED-BODY",
    })
    runner = OutboundAgentV1(gemini=fake_gemini, ledger=ledger)
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([ConsoleEmailAdapter()]),
        agent_runners={OutboundAgentV1.runner_kind: runner},
    )
    eng, _agent = _seed(store, prospects=2)

    rt.plan_all()
    pending = list(store.list_jobs_by_state(JobState.PENDING.value, engagement_id=eng.id))
    assert len(pending) == 2
    for job in pending:
        # Pre-rendered subject + body baked in.
        assert job.payload.get("subject") == "PERSONALIZED-SUBJECT"
        assert job.payload.get("body_text") == "PERSONALIZED-BODY"
        assert job.payload.get("personalized") is True
        used = set(job.payload.get("personalization_used_fields") or [])
        assert "first_name" in used
        assert "company" in used

    # LLM cost was debited (one debit per planned job).
    assert ledger.total_spent_cents(eng.id, category="llm") >= 2
    # Two calls to Gemini (one per prospect).
    assert len(fake_gemini.calls) == 2


def test_agent_without_gemini_uses_template_path(storage):
    """Backward compat: phase 1 behavior preserved when no Gemini wired."""
    store, events, ledger = storage
    runner = OutboundAgentV1()  # no gemini, no ledger
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([ConsoleEmailAdapter()]),
        agent_runners={OutboundAgentV1.runner_kind: runner},
    )
    eng, _agent = _seed(store, prospects=1)

    rt.plan_all()
    pending = list(store.list_jobs_by_state(JobState.PENDING.value, engagement_id=eng.id))
    assert len(pending) == 1
    job = pending[0]
    # Templates passed through, no pre-rendered subject/body.
    assert "subject" not in job.payload  # adapter will render at execute time
    assert "body_text" not in job.payload
    assert job.payload["subject_template"].startswith("Quick question")
    # Personalization metadata absent.
    assert "personalized" not in job.payload


def test_agent_personalize_fallback_still_produces_a_job(storage):
    """If Gemini fails, the Job is still planned with the templated content."""
    store, events, ledger = storage
    failing = _FakeGemini(GeminiError("api down"))
    runner = OutboundAgentV1(gemini=failing, ledger=ledger)
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([ConsoleEmailAdapter()]),
        agent_runners={OutboundAgentV1.runner_kind: runner},
    )
    eng, _agent = _seed(store, prospects=1)

    rt.plan_all()
    pending = list(store.list_jobs_by_state(JobState.PENDING.value, engagement_id=eng.id))
    assert len(pending) == 1
    job = pending[0]
    # Fallback baked the placeholder-substituted templates as the rendered
    # subject/body — sends still go out.
    assert "Alice" in job.payload["subject"]
    assert "The offer" in job.payload["body_text"]
    assert job.payload.get("personalized") is False
    assert "api down" in (job.payload.get("personalization_error") or "")
    # No LLM cost debited (fallback emits 0).
    assert ledger.total_spent_cents(eng.id, category="llm") == 0


def test_agent_personalize_disabled_via_config(storage):
    """Operator can turn off personalization on a per-engagement basis."""
    store, events, ledger = storage
    fake_gemini = _FakeGemini({"subject": "PERSONAL", "body": "BODY"})
    runner = OutboundAgentV1(gemini=fake_gemini, ledger=ledger)
    rt = EngineRuntime(
        store=store, events=events, ledger=ledger,
        adapters=AdapterRegistry([ConsoleEmailAdapter()]),
        agent_runners={OutboundAgentV1.runner_kind: runner},
    )
    eng, _ = _seed(store, prospects=1)
    # Override agent config: personalize=False
    agent = store.get_agent("agent_p")
    cfg = dict(agent.config)
    cfg["personalize"] = False
    store.save_agent(Agent(
        id=agent.id, engagement_id=agent.engagement_id,
        runner_kind=agent.runner_kind, config=cfg,
        status=agent.status, created_at=agent.created_at,
    ))

    rt.plan_all()
    pending = list(store.list_jobs_by_state(JobState.PENDING.value, engagement_id=eng.id))
    assert "subject" not in pending[0].payload  # template path
    assert fake_gemini.calls == []
