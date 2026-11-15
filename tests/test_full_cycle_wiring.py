"""Full-Cycle wiring: List/ICP → SourceAgent → email send via connected mailbox."""

from __future__ import annotations

from fastapi.testclient import TestClient

from engine.agents.outbound_agent import effective_sequence, step_is_linkedin
from engine.adapters.email_gmail_real import GmailMailer, RealGmailSendAdapter
from engine.core.state import JobState
from engine.services.people_discovery import DiscoveredBuyer, PeopleDiscoveryResult


def test_gmail_mailer_is_real_gmail_adapter():
    assert issubclass(GmailMailer, RealGmailSendAdapter)
    assert GmailMailer.name == "email.gmail_mailer"


def test_linkedin_first_sequence_skips_to_email_without_seat():
    seq = [
        {"type": "visitProfile", "channel": "linkedin", "wait_days": 0},
        {"type": "invitationNote", "channel": "linkedin", "wait_days": 1},
        {"type": "email", "channel": "email", "wait_days": 4, "subject_template": "Hi {first_name}"},
    ]
    collapsed, notes = effective_sequence(seq, has_linkedin_seat=False)
    assert notes == ["skipped_linkedin_no_seat"]
    assert len(collapsed) == 1
    assert collapsed[0]["channel"] == "email"
    assert collapsed[0]["wait_days"] == 0
    assert not step_is_linkedin(collapsed[0])

    kept, notes_with_seat = effective_sequence(seq, has_linkedin_seat=True)
    assert notes_with_seat == []
    assert len(kept) == 3


def test_linkedin_only_sequence_synthesizes_email_fallback():
    seq = [
        {"type": "invitation", "channel": "linkedin"},
        {"type": "message", "channel": "linkedin"},
    ]
    collapsed, notes = effective_sequence(seq, has_linkedin_seat=False)
    assert "skipped_linkedin_no_seat" in notes
    assert "synthesized_email_fallback" in notes
    assert collapsed[0]["channel"] == "email"


def _auth_client(tmp_path, monkeypatch, people):
    def fake_discover(**kwargs):
        return PeopleDiscoveryResult(
            people=list(people),
            queries=['site:linkedin.com/in/ "VP Sales"'],
            status="complete",
            message="Found buyers from public people search.",
            cap=20,
        )

    monkeypatch.setattr("engine.services.people_discovery.discover_people_for_icp", fake_discover)
    from cockpit import create_app

    app = create_app(db_url=f"sqlite:///{tmp_path / 'full_cycle.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    res = client.post(
        "/api/auth/signup",
        json={
            "email": "founder@fullcycle.test",
            "password": "Password1!",
            "full_name": "Ada Founder",
            "company_name": "Full Cycle Co",
        },
    )
    assert res.status_code == 200, res.text
    return client, {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_launch_enqueues_source_agent_and_writes_prospects(tmp_path, monkeypatch):
    people = [
        DiscoveredBuyer(
            first_name="Priya",
            last_name="Rao",
            full_name="Priya Rao",
            title="VP Sales",
            company="Northwind",
            company_domain="northwind.io",
            linkedin_url="https://www.linkedin.com/in/priya-rao-gtm",
            email="priya.rao@northwind.io",
        ),
        DiscoveredBuyer(
            first_name="Jonah",
            last_name="Kim",
            full_name="Jonah Kim",
            title="Head of Revenue",
            company="Harbor Labs",
            company_domain="harborlabs.com",
            linkedin_url="https://www.linkedin.com/in/jonah-kim-rev",
            email="",
        ),
    ]
    client, headers = _auth_client(tmp_path, monkeypatch, people)
    created = client.post(
        "/api/campaigns",
        headers=headers,
        json={
            "customer_name": "Full Cycle Agent",
            "offer": "Book meetings",
            "icp_description": "VP Sales at B2B SaaS",
            "target_job_titles": ["VP Sales", "Head of Revenue"],
            "search_keywords": ["outbound", "intent"],
            "sequence": [
                {"kind": "visitProfile", "delay": "Day 0"},
                {"kind": "invitationNote", "delay": "Day 1"},
                {"kind": "email", "delay": "Day 4"},
            ],
            "auto_discover_people": True,
            "discovery_cap": 20,
            "min_lead_score": 0.6,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["people_discovery"]["status"] == "complete"
    assert body["people_discovery"]["created"] == 2
    assert body["sequence"][0]["type"] == "visitProfile"
    campaign_id = body["id"]

    summary = client.get(f"/api/contacts/summary?campaign_id={campaign_id}", headers=headers).json()
    assert summary["total"] == 2
    assert summary["with_email"] == 1
    rows = client.get(f"/api/contacts?campaign_id={campaign_id}", headers=headers).json()["data"]
    assert {r["full_name"] for r in rows} == {"Priya Rao", "Jonah Kim"}


def test_copilot_approve_sends_email_immediately_despite_low_score(tmp_path, monkeypatch):
    people = [
        DiscoveredBuyer(
            first_name="Priya",
            last_name="Rao",
            full_name="Priya Rao",
            title="VP Sales",
            company="Northwind",
            company_domain="northwind.io",
            linkedin_url="https://www.linkedin.com/in/priya-rao-gtm",
            email="priya.rao@northwind.io",
        ),
    ]
    client, headers = _auth_client(tmp_path, monkeypatch, people)
    created = client.post(
        "/api/campaigns",
        headers=headers,
        json={
            "customer_name": "Copilot Send",
            "offer": "Book a demo",
            "icp_description": "VP Sales",
            "target_job_titles": ["VP Sales"],
            "search_keywords": ["outbound"],
            "sequence": [
                {"kind": "invitationNote", "channel": "linkedin", "delay": "Day 0"},
                {
                    "kind": "email",
                    "channel": "email",
                    "delay": "Day 4",
                    "subject_template": "quick question, {first_name}",
                    "body_template": "Hi {first_name}, {offer}",
                },
            ],
            "hitl_threshold": 50,
            "personalize_enabled": False,
            "auto_discover_people": True,
            "min_lead_score": 0.99,
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    store = client.app.state.store
    prospect = next(p for p in store.list_prospects(campaign_id, limit=10) if p.email)
    research = dict(prospect.research or {})
    research.update({"scoring": 0.03, "intent_scoring": 0.0, "total_scoring": 0.03, "fit": "out-of-scope"})
    from engine.core.types import Prospect

    store.save_prospect(
        Prospect(
            id=prospect.id,
            engagement_id=prospect.engagement_id,
            email=prospect.email,
            full_name=prospect.full_name,
            company=prospect.company,
            title=prospect.title,
            raw=dict(prospect.raw or {}),
            research=research,
            status=prospect.status,
            created_at=prospect.created_at,
        )
    )

    tick = client.post(f"/api/campaigns/{campaign_id}/tick", headers=headers)
    assert tick.status_code == 200, tick.text
    detail = client.get(f"/api/campaigns/{campaign_id}", headers=headers).json()
    awaiting = detail.get("jobs_awaiting_approval") or []
    assert awaiting, "LinkedIn-first sequence with no seat must still queue an email for Copilot"
    job_id = awaiting[0]["id"]
    assert awaiting[0].get("score_gate") is False

    approve = client.post(f"/api/campaigns/{campaign_id}/approve-job/{job_id}", headers=headers)
    assert approve.status_code == 200, approve.text
    payload = approve.json()
    assert payload["ok"] is True
    assert payload["sent"] is True
    assert payload["channel"] == "email"
    job = store.get_job(job_id)
    assert job.state == JobState.SUCCEEDED.value
