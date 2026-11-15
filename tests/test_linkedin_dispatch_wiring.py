"""LinkedIn Voyager dispatch wiring (Gojiberry-style steps)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from engine.agents.outbound_agent import OutboundAgentV1, step_is_linkedin
from engine.core.types import Agent, EventKind, JobKind
from engine.dispatch.linkedin_adapter import LinkedInVoyagerAdapter, normalize_voyager_step_type


def test_normalize_voyager_step_types():
    assert normalize_voyager_step_type("VISIT_PROFILE") == "visitProfile"
    assert normalize_voyager_step_type("LIKE_POSTS") == "likePosts"
    assert normalize_voyager_step_type("COMMENT_ON_POST") == "commentOnPost"
    assert normalize_voyager_step_type("LINKEDIN_CONNECT") == "invitationNote"
    assert normalize_voyager_step_type("CONNECTION_NOTE") == "invitationNote"
    assert normalize_voyager_step_type("LINKEDIN_MESSAGE") == "message"
    assert step_is_linkedin({"kind": "COMMENT_ON_POST", "channel": "linkedin"})


def test_linkedin_adapter_runs_invitation(monkeypatch):
    store = MagicMock()
    store.get_engagement_tenant_id.return_value = "t1"
    events = MagicMock()
    adapter = LinkedInVoyagerAdapter(store=store, events=events)

    fake_provider = MagicMock()
    fake_provider.has_cookie = True
    fake_provider.mode = "live_voyager"
    fake_provider.send_invitation_sync.return_value = {
        "ok": True,
        "mode": "live_voyager",
        "inviteeProfileUrn": "urn:li:fsd_profile:ABC",
    }
    monkeypatch.setattr(
        "engine.dispatch.linkedin_adapter.get_active_linkedin_provider",
        lambda *a, **k: fake_provider,
    )

    job = SimpleNamespace(
        id="job_li_1",
        engagement_id="eng1",
        agent_id="ag1",
        prospect_id="p1",
        kind=JobKind.LINKEDIN_ACTION,
        payload={
            "channel": "linkedin",
            "step_type": "invitationNote",
            "linkedin_url": "https://www.linkedin.com/in/ada",
            "body_text": "Loved your post on outbound",
            "tenant_id": "t1",
        },
    )
    ctx = MagicMock()
    result = adapter.execute(job, context=ctx)
    assert result.succeeded
    assert result.output.get("step_type") == "invitationNote"
    fake_provider.send_invitation_sync.assert_called_once()
    ctx.emit.assert_called_once()
    assert ctx.emit.call_args.args[0].kind == EventKind.LINKEDIN_SENT


def test_outbound_plans_linkedin_job_when_seat_and_url(monkeypatch):
    monkeypatch.setattr(
        "engine.dispatch.linkedin.tenant_has_linkedin_seat",
        lambda store, tid: True,
    )
    store = MagicMock()
    store.get_engagement_tenant_id.return_value = "tenant-1"

    engagement = SimpleNamespace(
        id="eng-1",
        status="active",
        offer="Attainly",
        icp_description="B2B founders",
    )
    prospect = SimpleNamespace(
        id="p-1",
        email="",
        full_name="Ada Lovelace",
        company="Analytical Engines",
        title="Founder",
        status="new",
        raw={"linkedin_url": "https://www.linkedin.com/in/ada", "first_name": "Ada"},
        research={},
    )
    agent = Agent(
        id="ag-1",
        engagement_id="eng-1",
        runner_kind=OutboundAgentV1.runner_kind,
        config={
            "sequence": [
                {"kind": "VISIT_PROFILE", "channel": "linkedin", "wait_days": 0},
                {"kind": "EMAIL", "channel": "email", "wait_days": 2, "subject_template": "Hi {first_name}"},
            ],
            "hitl_threshold": 50,
            "plan_batch_size": 5,
            "personalize": False,
            "message_mode": "template",
        },
    )

    ctx = MagicMock()
    ctx.get_engagement.return_value = engagement
    ctx.list_recent_events.return_value = []
    ctx.list_prospects.side_effect = lambda *a, **k: [prospect] if k.get("status") == "new" else []
    ctx._store = store

    jobs = list(OutboundAgentV1().plan(agent, context=ctx))
    assert len(jobs) == 1
    assert jobs[0].kind == JobKind.LINKEDIN_ACTION
    assert jobs[0].payload["channel"] == "linkedin"
    assert jobs[0].payload["step_type"] == "visitProfile"
    assert jobs[0].payload["linkedin_url"].endswith("/ada")
